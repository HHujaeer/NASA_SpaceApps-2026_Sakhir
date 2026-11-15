Place the standardized NASA experiment CSV files here (one *.csv file per
investigation). The file name (without .csv) becomes the investigation id.

Each row is one record (test/run). Recognised column names are configured in
config.py (FIELD_ALIASES): experiment name, material/fuel, oxygen, pressure,
flow, gravity, sensors, objective, mission, source/reference, findings, notes.
Any other numeric column is treated as a measurement. Unknown columns are kept
and searchable. Missing cells ("", NA, N/A, null, -, ...) are reported as null.

Include units in column names (e.g. Pressure_kPa, O2_pct) so values can be
normalised for comparison. Without a unit the values are still returned
as-is but are not converted or compared numerically across files.
