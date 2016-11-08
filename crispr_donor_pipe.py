"""Creates primers using refseq ID list and master table

Usage: ./crispr_donor_pipe.py (<config> <list> <LR_len> <RF_len> <min> <max>) [options]

Arguments:
    <config>    json formatted config file with refs and tool locations
    <list>      list of refSeq IDs, one per line
    <LR_len>    length of left reverse sequence primer to try
    <RF_len>    length of right forward sequence primer to try
    <min>       min length to use when trying to find an alternative primer
    <max>       max length to use when trying to find an alternative primer

Options:
    -h --help

"""
from docopt import docopt
import gzip
import time
from datetime import datetime
import subprocess
import json

args = docopt(__doc__)


def parse_config(config_file):
    config_data = json.loads(open(config_file, 'r').read())
    return config_data['primer3'], config_data['master'], config_data['Lsettings'], config_data['Rsettings'], \
           config_data['lf_gibson'], config_data['lr_gibson'], config_data['rf_gibson'], config_data['rr_gibson']


def populate_seq_dict(id_dict, master, err):
    seq_info = {}
    cur = gzip.open(master)
    next(cur)
    for entry in cur:
        entry = entry.rstrip('\n').split('\t')
        id_list = entry[0].split(',')
        gene_list = entry[1].split(',')
        for i in xrange(0, len(id_list), 1):
            nm = id_list[i]
            if nm in id_dict:
                id_dict[nm] = 1
                seq_info[nm] = {}
                seq_info[nm]['gene'] = gene_list[i]
                seq_info[nm]['seq'] = entry[2:]
                break
    for nm in id_dict:
        if id_dict[nm] == 0:
            err.write(nm + ' not found, skipping!\n')
    return seq_info


def rev_comp(seq):
    code = {'A': 'T', 'T': 'A', 'C': 'G', 'G': 'C'}
    new_seq = ''
    for i in xrange(0, len(seq), 1):
        new_seq += code[seq[i]]
    return new_seq[::-1]


def create_seq(nm, info, LR_len, RF_len):
        l_input_file = temp_dir + nm + '_LEFT_SEQUENCE.txt'
        r_input_file = temp_dir + nm + '_RIGHT_SEQUENCE.txt'
        left = open(l_input_file, 'w')
        lr_prime = info['seq'][0][(int(LR_len) * -1):]
        lr_prime = rev_comp(lr_prime)
        left.write('SEQUENCE_ID=' + nm + '\nSEQUENCE_TEMPLATE=' + info['seq'][0] + '\nSEQUENCE_PRIMER_REVCOMP='
                   + lr_prime + '\nSEQUENCE_TARGET=37,21\n=')
        left.close()
        rf_prime = info['seq'][1][:(int(RF_len))]
        right = open(r_input_file, 'w')
        right.write('SEQUENCE_ID=' + nm + '\nSEQUENCE_TEMPLATE=' + info['seq'][1] + '\nSEQUENCE_PRIMER='
                   + rf_prime + '\nSEQUENCE_TARGET=37,21\n=')
        right.close()
        return l_input_file, r_input_file


def parse_results(output, forward, reverse, side, gene):
    f_primer = ''
    r_primer = ''
    attr_dict = {'PRIMER_LEFT_0_PROBLEMS': '', 'PRIMER_LEFT_0_TM': '', 'PRIMER_RIGHT_0_PROBLEMS': '',
                 'PRIMER_RIGHT_0_TM': ''}
    f = 0
    for result in open(output):
        cur = result.rstrip('\n').split('=')
        if cur[0] in attr_dict:
            attr_dict[cur[0]] = cur[1]
        if side == 'Left' and cur[0] == 'SEQUENCE_PRIMER_REVCOMP':
            r_primer = cur[1]
        elif side == 'Left' and cur[0] == 'PRIMER_LEFT_0_SEQUENCE':
            f_primer = cur[1]
            f = 1
            #break
        if side == 'Right' and cur[0] == 'SEQUENCE_PRIMER':
            f_primer = cur[1]
        elif side == 'Right' and cur[0] == 'PRIMER_RIGHT_0_SEQUENCE':
            r_primer = cur[1]
            f = 1
            #break
    return '\t'.join((gene + '.' + side + '.F', forward + f_primer, attr_dict['PRIMER_LEFT_0_PROBLEMS'],
                      attr_dict['PRIMER_LEFT_0_TM'], gene + '.' + side + '.R', reverse + r_primer,
                      attr_dict['PRIMER_RIGHT_0_PROBLEMS'], attr_dict['PRIMER_RIGHT_0_TM'])), f,


def run_primer3(input, output, settings, primer3):
    cmd = primer3 + ' -p3_settings_file=' + settings + ' -output=' + output + ' ' + input
    subprocess.call(cmd, shell=True)


def setup_primer3(seq_dict, primer3, Lsettings, Rsettings, temp_dir, LR_len, RF_len, lf_gibson, lr_gibson, rf_gibson,
                  rr_gibson, tbl, min_len, max_len):
    for nm in seq_dict:
        (l_input_file, r_input_file) = create_seq(nm, seq_dict[nm], LR_len, RF_len)
        l_output_file = temp_dir + nm + '_LEFT_PRIMER3_RESULTS.txt'
        r_output_file = temp_dir + nm + '_RIGHT_PRIMER3_RESULTS.txt'
        gene = seq_dict[nm]['gene']
        run_primer3(l_input_file, l_output_file, Lsettings, primer3)
        run_primer3(r_input_file, r_output_file, Rsettings, primer3)
        # parse results, if primer not found, adjust length and try again
        (left_str, left_flag) = parse_results(l_output_file, lf_gibson, lr_gibson, 'Left',  gene)
        (right_str, right_flag) = parse_results(r_output_file, rf_gibson, rr_gibson, 'Right', gene)
        tbl.write(nm + '\t' + left_str + '\t' + right_str + '\n')


(primer3, master, Lsettings, Rsettings, lf_gibson, lr_gibson, rf_gibson, rr_gibson) = parse_config(args['<config>'])
(LR_len, RF_len, min_len, max_len) = (args['<LR_len>'], args['<RF_len>'], args['<min>'], args['<max>'])
timestamp = time.strftime("%Y-%m-%d_%H%M") + '_' + LR_len + '_' + RF_len
warnings = open(timestamp + '_warnings.txt', 'w')
tbl = open(timestamp + '_results.xls', 'w')
temp_dir = timestamp + '_TEMP/'
subprocess.call('mkdir ' + temp_dir, shell=True)


header = 'RefSeq ID \tDonor Left join F\tDonor Left join F oligo sequence\tLF_Problems\tLF_TM\tDonor Left join R\t' \
         'Donor Left join R oligo sequence\tLR_Problems\tLR_TM\tDonor Right join F\tDonor Right join F oligo sequence' \
         '\tRF_Problems\tRF_TM\tDonor Right join R\tDonor Right join R oligo sequence\tRR_Problems\tRR_TM\n'
tbl.write(header)
id_dict = {}
# set up transcript list
for line in open(args['<list>']):
    line = line.rstrip('\n')
    id_dict[line] = 0
# get relevant seqs from table
seq_dict = populate_seq_dict(id_dict, master, warnings)
setup_primer3(seq_dict, primer3, Lsettings, Rsettings, temp_dir, LR_len, RF_len, lf_gibson, lr_gibson, rf_gibson,
              rr_gibson, tbl, min_len, max_len)
tbl.close()
