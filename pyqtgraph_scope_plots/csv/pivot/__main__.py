# Copyright 2025 Enphase Energy, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import argparse
import csv
import os.path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Convert a CSV from a long format (with one row per reading, '
                                                 'readings from multiple sources in the same file and identified '
                                                 'by a column value) to a wide format (with one column per source). '
                                                 'Rows are combined when the first column value is identical. '
                                                 'Columns are prefixed with the source name. '
                                                 'Used to pre-process long format data for use with the CSV viewer.')
    parser.add_argument('csv', type=str,
                        help='Input CSV data file.')
    parser.add_argument('source_col', type=str,
                        help='Column name identifying the source of the row, aka the pivot column.')
    parser.add_argument('--append_source', action="store_true", default=False,
                        help='Append the source name to the column names in the output CSV.')

    args = parser.parse_args()

    with open(args.csv, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        table = [row for row in reader]

    assert args.source_col in reader.fieldnames
    index_fieldname = reader.fieldnames[0]
    data_fieldnames = list(reader.fieldnames[1:])  # drop index field
    data_fieldnames.remove(args.source_col)

    source_values = list(dict.fromkeys(row[args.source_col] for row in table))  # order-preserving
    output_files_by_source = {}
    csv_by_source = {}
    input_filename, input_ext = os.path.splitext(args.csv)
    for source_name in source_values:
        output_filename = f"{input_filename}_{source_name}{input_ext}"
        output_file = open(output_filename, 'w', newline='')
        output_files_by_source[source_name] = output_file

        if args.append_source:
            this_data_fieldnames = [f"{fieldname}_{source_name}" for fieldname in data_fieldnames]
        else:
            this_data_fieldnames = data_fieldnames
        writer = csv.DictWriter(output_file, fieldnames=[index_fieldname] + this_data_fieldnames)
        csv_by_source[source_name] = writer
        writer.writeheader()

    for row in table:
        source_name = row[args.source_col]

        if args.append_source:
            row_data = {f"{field}_{source_name}": row[field] for field in data_fieldnames}
        else:
            row_data = {field: row[field] for field in data_fieldnames}
        csv_by_source[source_name].writerow(
            {index_fieldname: row[index_fieldname], **row_data}
        )

    for _, output_file in output_files_by_source.items():
        output_file.close()
