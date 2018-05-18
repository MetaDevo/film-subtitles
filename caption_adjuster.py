""" Automatically adjust the timecodes of subtitles in an SCC (Scenarist) caption file.
This is useful if you have made subtitles at the time of appearance and need them
adjusted to account for SCC's buffer loading times. Without taking into account the
buffer times, the subtitles will display late by an amount that differs per subtitle.
"""
__author__ = 'skenyon'
import argparse
import copy
import math

file_header = ["Scenarist_SCC V1.0"]
time_separators = [":", ";"]

FILLER = "80"
ENM = "94ae"  # ENM (Erase Non-displayed buffer Memory)
RCL = "9420"  # RCL (Resume Caption Loading)
EOC = "942f"  # EOC (End of Caption)
EDM = "942c"  # EDM (Erase Displayed Memory)
PAC_FIRST_BYTE = ["91", "92", "15", "16", "97", "10", "13", "94"]

FRAMES_PER_SECOND_LOGICAL = 30  # 29.97 timecode is the standard time format for SCC
BUFFER_FRAMES_PER_CHAR = 0.8  # seems like it drifts from 0.8 at start to
MIN_CAPTION_SECONDS = 1.0
MAX_SUBTITLE_LINE_CHARS = 32

# Without this (i.e. set it to zero) you can get errors when validating the generated SCC file,
# presumably for having too many characters per second.
LARGE_CAPTION_EXTRA_LIMIT_FRAMES = FRAMES_PER_SECOND_LOGICAL / 2.0

# Allow removing EDM (clear) codes if gaps become too small.
ALLOW_EDM_REMOVAL = True
MIN_GAP_SECONDS = 2.0

# Prevent drift over time due to how timecodes are processed
DROP_FRAME = True

removed_timecodes = []


class Timecode(object):
    _FRAMES_PER_MINUTE = FRAMES_PER_SECOND_LOGICAL * 60
    _FRAMES_PER_HOUR = _FRAMES_PER_MINUTE * 60

    def __init__(self, timecode_str=None, is_edm=False):
        self._hours = 0
        self._minutes = 0
        self._seconds = 0
        self._frames = 0
        self._delim = ':'
        self._is_edm = is_edm
        if timecode_str is not None:
            self.from_string(timecode_str)

    @property
    def is_edm(self):
        """
        @return True if this is a timecode for a clear command instead of an actual subtitle.
        """
        return self._is_edm

    def from_string(self, timecode_str):
        self._hours = int(timecode_str[0:2])
        self._minutes = int(timecode_str[3:5])
        self._seconds = int(timecode_str[6:8])
        self._frames = int(timecode_str[9:11])

    def to_string(self):
        stringified = ""
        chunks = [self._hours, self._minutes, self._seconds, self._frames]
        for v in chunks:
            stringified += '%.2d' % v + self._delim

        if DROP_FRAME:
            listified = list(stringified)
            listified[8] = ';'
            stringified = "".join(listified)

        return stringified[:-1]

    def to_frames(self):
        return int(self._hours * self._FRAMES_PER_HOUR + self._minutes * self._FRAMES_PER_MINUTE +
                   self._seconds * FRAMES_PER_SECOND_LOGICAL + self._frames)

    def from_frames(self, frames):
        self._hours = frames // self._FRAMES_PER_HOUR
        frames %= self._FRAMES_PER_HOUR
        self._minutes = frames // self._FRAMES_PER_MINUTE
        frames %= self._FRAMES_PER_MINUTE
        self._seconds = frames // FRAMES_PER_SECOND_LOGICAL
        frames %= FRAMES_PER_SECOND_LOGICAL
        self._frames = frames

    def add_seconds(self, seconds):
        self._seconds += seconds
        if self._seconds >= 60:
            self._seconds = 60 - self._seconds
            self.add_minutes(1)

    def add_minutes(self, minutes):
        self._minutes += minutes
        if self._minutes >= 60:
            self._minutes = 60 - self._minutes
            self.add_hours(1)

    def add_hours(self, hours):
        self._hours += hours
        if self._hours > 99:
            print "Error: Hit max hours"
            exit()

    def subtract_frames(self, frames):
        total_frames = self.to_frames() - frames
        self.from_frames(total_frames)

    def add_frames(self, frames):
        total_frames = self.to_frames() + frames
        self.from_frames(total_frames)


def parse_enm(token):
    return token == ENM


def parse_rcl(token):
    return token == RCL


def parse_pac(token):
    first_byte = token[0:2]
    return first_byte in PAC_FIRST_BYTE


def count_token(token):
    # Assume text unless there's a PAC (Preamble Address Code)(used for positioning) mixed in.
    if parse_pac(token):
        return 0
    else:
        count = 0
        for byte in [token[0:2], token[2:4]]:
            if byte != FILLER:
                count += 1
        return count

# handle the commands (which are in 2-byte chunks)
scc_popon_parse = {
    0: parse_enm,
    1: parse_rcl,
    2: parse_pac
}


def parse_caption(tokens):
    prev_token = ""
    state = 0
    char_count = 0
    for i, token in enumerate(tokens):
        if token == prev_token:
            continue
        prev_token = token
        if state <= 2:
            ok = scc_popon_parse[state](token)
            if not ok:
                print "ERROR: parsing"
                exit()
            state += 1
        else:
            char_count += count_token(token)
    return char_count


# return estimated buffer load time in integer frames
def buffer_load_frames(char_count):
    return math.ceil(char_count * BUFFER_FRAMES_PER_CHAR)


def adjust_timecode(prev_timecode, old_timecode, buffer_time, char_count):
    new_timecode = copy.copy(old_timecode)
    new_timecode.subtract_frames(buffer_time)
    remove_prev = False
    is_edm = False
    if prev_timecode is not None:
        limit = copy.copy(prev_timecode)
        if ALLOW_EDM_REMOVAL and prev_timecode.is_edm:
            is_edm = True
            limit.add_seconds(MIN_GAP_SECONDS)
        else:
            limit.add_seconds(MIN_CAPTION_SECONDS)
            # It's a big one so give it so more space
            if char_count >= MAX_SUBTITLE_LINE_CHARS:
                limit.add_frames(LARGE_CAPTION_EXTRA_LIMIT_FRAMES)

        if new_timecode.to_frames() < limit.to_frames():
            if is_edm:
                # If we get too close to a previous clear, then remove the clear and start the new
                # subtitle there without a gap.
                remove_prev = True
                new_timecode = prev_timecode
            else:
                new_timecode = limit

    actual_change = old_timecode.to_frames() - new_timecode.to_frames()
    if actual_change < 0:
        actual_change = 0
    if buffer_time != actual_change:
        print "Can't move full buffer time (%d frames). Actual move: %d frames" % (buffer_time,
                                                                                   actual_change)
    return new_timecode, actual_change, remove_prev


def update_timecode(line, timecode):
    return timecode.to_string() + line[11:]


def adjust_timecodes(input_filename, output_filename):
    with open(input_filename, 'r') as infile, open(output_filename, 'w') as outfile:
        prev_timecode = None
        prev_adjust_frames = 0
        prev_filepos = 0
        prev_char_count = 0
        for line in infile:
            new_timecode = None
            timecode_str = ""
            char_count = 0
            if line.strip() not in file_header:
                tokens = line.replace('\t', ' ').split(' ')
                timecode_str = tokens[0]
                cap_tokens = tokens[1:]

                if cap_tokens:
                    if cap_tokens[0].strip() == EDM:
                        print "clear time: %s, prev adjust: %d" % (timecode_str, prev_adjust_frames)
                        new_timecode = Timecode(timecode_str, is_edm=True)
                        # notice we DO NOT shift the EDM timecode as it doesn't need any buffer time
                    else:
                        char_count = parse_caption(cap_tokens)
                        print "\nstart time:", timecode_str, " char count: ", char_count
                        buffer_time = buffer_load_frames(char_count)
                        new_timecode, prev_adjust_frames, remove_prev = adjust_timecode(
                            prev_timecode,
                            Timecode(timecode_str),
                            buffer_time,
                            prev_char_count)
                        print "Adjustment: minus %d frames" % prev_adjust_frames
                        if remove_prev:
                            print "Removing previous line."
                            removed_timecodes.append(prev_timecode)
                            outfile.seek(prev_filepos)
                            outfile.truncate()

            if new_timecode is not None:
                print "Updating timecode from %s to %s" % (timecode_str, new_timecode.to_string())
                prev_timecode = copy.copy(new_timecode)
                line = update_timecode(line, new_timecode)
                prev_filepos = outfile.tell()
                prev_char_count = char_count
            else:
                if line.strip() != "":
                    print "Warning: line has no timecode: ", line.strip()
            outfile.write(line)

print "Closed Caption Adjuster\n"

parser = argparse.ArgumentParser()
parser.add_argument("input_file", help="Input file")
parser.add_argument("output_file", help="Output file")
args = parser.parse_args()

input_filename = args.input_file
output_filename = args.output_file

if not input_filename:
    print "ERROR: Need an input filename."
    exit()
elif not output_filename:
    print "ERROR: Need an output filename."
    exit()

print "Processing..."
adjust_timecodes(input_filename, output_filename)

print "\nDone.\n"
print "Removed timecodes: "
for i, t in enumerate(removed_timecodes):
    print i, ": ", t.to_string()