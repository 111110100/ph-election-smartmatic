# ph-election-smartmatic
Script to process election data sent by Smartmatic machines. The original was written using Pandas and is owned by Inquirer Interactive. This version will be using Polars. To get the sample data, you need to get in touch with the Comelec office or create your own dummy data.
## Requirements
- Python 3
- Polars
- TQDM
## Command line interface
### Run all commands below (generate everything)
```shell
python batch_generate.py all
```
### Compute local contests (e.g. Governor, Vice-Governor, etc)
```shell
python batch_generate.py tally-local
```
### Compute national contests (e.g. President, VP, Senator, Party List)
```shell
python batch_generate.py tally-national
```
### Compute leading national candidate per province
```shell
python batch_generate.py leading-candidate-province
```
### Compute national candidate per province
```shell
python batch_generate.py tally-national-province
```
### Compute stats for map data
```shell
python batch_generate.py stats
```
### Run script in interactive mode
```shell
python -i batch_generate.py read_results
```
## Files and fields
The files are in CSV format, separated by the **pipe** character **"|"**.
### CANDIDATES.CSV
|CONTEST_CODE|CANDIDATE_CODE|CANDIDATE_NAME|
|-|-|-|
00000000|0000000000|"JOSE RIZAL (IND)"
### CONTESTS.CSV
|CONTEST_CODE|CONTEST_NAME|
|-|-|
|00000000|PRESIDENT PHILIPPINES
### PARTIES.CSV
|PARTIES_CODE|PARTIES_NAME|PARTIES_ALIAS|
|-|-|-|
|000|INDEPENDENT|IDP|
### PRECINCTS.CSV
|VCM_ID|REG_NAME|PRV_NAME|MUN_NAME|BRGY_NAME|POLLPLACE|CLUSTERED_PREC|REGISTERED_VOTERS|
|-|-|-|-|-|-|-|-|
00000000|REGION I|ILOCOS NORTE|ADAMS|ADAMS (POB.)|ADAMS CENTRAL ELEMENTARY SCHOOL|00000000|000
### RESULTS.CSV
|PRECINCT_CODE|CONTEST_CODE|CANDIDATE_CODE|PARTY_CODE|VOTES_AMOUNT|TOTALIZATION_ORDER|NUMBER_VOTERS|UNDERVOTE|OVERVOTE|RECEPTION_DATE|
|-|-|-|-|-|-|-|-|-|-|
|00000000|00000000|0000000000|0000000000|0|0|000|000|00|05/09/2022 - 08:07:08 PM|