"""Input a text version of a screenplay (I tested this using Trelby's text output format),
and output either a CSV or a transcript.
"""
__author__ = 'skenyon'
import csv
import argparse

# lead spaces mapping
sp_dialogue = 10
sp_charname = 22

offscreen_tokens = [" (V.O.)", " (O.S.)"]


# parse a line from a formatted text screenplay
def parse_line(line, line_num, write_data):
    charname = ""
    dialogue = ""

    return charname, dialogue


def output_transcript(input_text_filename, output_filename):
    def write_data(charname, dialogue, show_speaker):
        if len(charname) != 0 and len(dialogue) != 0:
            transcript_line = dialogue + "\n"
            if show_speaker:
                transcript_line = charname + ": " + transcript_line
            outfile.write(transcript_line)

    with open(input_text_filename, 'r') as txtfile, open(output_filename, 'wb') as outfile:
        line_num = 0
        charname = ""
        dialogue = ""
        is_offscreen = False

        for line in txtfile:
            line_num += 1
            data = line.lstrip()
            spacecount = len(line) - len(data)
            # at a new speaker, so we must be done with previous line
            if spacecount == sp_charname:
                # write the previous line...
                write_data(charname, dialogue, is_offscreen)
                # ... and start the new one
                is_offscreen = False
                charname = data.rstrip()
                for token in offscreen_tokens:
                    is_offscreen = is_offscreen or (charname.find(token) != -1)
                    charname = charname.replace(token, "")
                dialogue = ""
            elif spacecount == sp_dialogue:
                if dialogue:
                    separator = " "
                else:
                    separator = ""
                dialogue += separator + data.rstrip()
                if len(charname) == 0 and len(dialogue) == 0:
                    print "ERROR: input line #", line_num, " missing character name."
                    exit()
        # write the final line
        write_data(charname, dialogue, is_offscreen)


def output_csv(input_text_filename, output_csv_filename):
    def write_data(charname, dialogue):
        if len(charname) != 0 and len(dialogue) != 0:
            writer.writerow([charname, dialogue])

    with open(input_text_filename, 'r') as txtfile, open(output_csv_filename, 'wb') as csvfile:
        writer = csv.writer(csvfile, delimiter=',')
        writer.writerow(['Speaker', 'Dialogue'])
        line_num = 0
        charname = ""
        dialogue = ""
        for line in txtfile:
            line_num += 1
            data = line.lstrip()
            spacecount = len(line) - len(data)
            print "lead spaces:", spacecount
            if spacecount == sp_charname:
                write_data(charname, dialogue)
                charname = data.rstrip()
                charname = charname.replace(" (V.O.)", "")
                charname = charname.replace(" (O.S.)", "")
                dialogue = ""

            elif spacecount == sp_dialogue:
                if dialogue:
                    separator = " "
                else:
                    separator = ""
                dialogue += separator + data.rstrip()
                if len(charname) == 0 and len(dialogue) == 0:
                    print "ERROR: input line #", line_num, " missing character name."
                    exit()
        # write the final line
        write_data(charname, dialogue)


print "Script Converter\n"

parser = argparse.ArgumentParser()
parser.add_argument("input_file", help="Input file")
parser.add_argument("output_file", help="Output file")
parser.add_argument("-t", "--transcript", help="Transcript output mode", action="store_true")
args = parser.parse_args()

input_text_filename = args.input_file
output_filename = args.output_file

if not input_text_filename:
    print "ERROR: Need an input text filename."
    exit()
elif not output_filename:
    print "ERROR: Need an output filename."
    exit()

if args.transcript:
    print "Generating Transcript..."
    output_transcript(input_text_filename, output_filename)
else:
    print "Generating CSV..."
    output_csv(input_text_filename, output_filename)
