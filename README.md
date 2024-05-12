# ph-election-smartmatic
Script to process election data sent by Smartmatic machines. The original was written using Pandas and is owned by Inquirer Interactive. This version will be using Polars. To get the sample data, you need to get in touch with the Comelec office or create your own dummy data. **Some parts still need still need to be refactored.** Some parts were written in a Pandas way and not taking advantage of LazyFrame.
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
## Environment Variables
Set these environment variables on the command line or inside a .env file
```shell
# Turn on/off for parallel processing. Default False.
CONCURRENCY=True|T|1|False|F|0
# Turn on/off for progress bar display. Default True.
PROGRESS_BAR_TOGGLE=True|T|1|False|F|0
# Number of workers if CONCURRENCY is turned on. Uses os.cpu_count() or default to 8.
NUMBER_OF_WORKERS=8
# This is where the CSV files from Smartmatic is located.
WORKING_DIR=./var/
# This is where the generated files will be saved. It's WORKING_DIR + STATIC_DIR.
STATIC_DIR=static
```
## Files and fields generated
The files generated are in CSV format except for a few. These are:
- ***contest_code**.csv*: for all contests
- *map-**contest_code**.csv*: for leading condidate per province
- ***province_name**_**contest_code**.csv*: for results per province
- *map_stats.json*: contains VCM information from all provinces,
- *voter_stats.json*: contains votes & precincts information
- *vcm_received.csv*: contains cummulative VCM transmission over time
### contest_code.csv format
|CANDIDATE_NAME|VOTES_AMOUNT|PERCENTAGE|
|-|-|-|
|JOSE RIZAL (IND)|9|100.0|
### map-contest_code.csv format
|PRV_NAME|CANDIDATE_NAME|VOTES_AMOUNT|
|-|-|-|
|ABRA|JOSE RIZAL (IND)|9|
### province_name.csv format
|CANDIDATE_NAME|VOTES_AMOUNT|PERCENTAGE|
|-|-|-|
|JOSE RIZAL (IND)|9|100.0|
### map_stats.json
```json
{
    "PROVINCE_NAME": {
        "number_of_voters_not_transmitted":0,
        "total_clustered_precincts":0,
        "total_overvotes":0,
        "total_registered_voters":0,
        "total_undervotes":0,
        "total_voters":0,
        "vcm_not_transmitted":0,
        "vcm_transmitted":0,
        "vcm_transmitted_percentile":0.0,
        "voter_turnout":0.0
    }
}
```
### voter_stats.json
```json
{
    "total_number_of_overvotes":0,
    "total_number_of_precincts":0,
    "total_number_of_registered_voters":0,
    "total_number_of_reporting_precincts":0,
    "total_number_of_undervotes":0,
    "total_number_of_voters":0
}
```
### vcm_received.csv
|RECEPTION_DATE|VCM_RECEIVED|
|-|-|
|05/09/2022 - 07:08:48 PM|xxx
|05/09/2022 - 07:08:49 PM|xxxx
|05/09/2022 - 07:08:51 PM|xxxxx
|05/09/2022 - 07:08:52 PM|xxxxxx
Information can be used to plot received VCMs over time:
![VCMs received over time](https://raw.githubusercontent.com/111110100/ph-election-smartmatic/main/vcms_received.png)
## Files and fields received from Transparency Server
The files coming from Transparency server are in CSV format, separated by the **pipe** character **"|"**.
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
## Benchmarks
The tests were run on a base model MacBook Air M2. Data based from 32 Million rows of election data.
### Pandas
![Pandas benchmark result](https://raw.githubusercontent.com/111110100/ph-election-smartmatic/main/pandas.png)
### Polars
![Polars benchmark result](https://raw.githubusercontent.com/111110100/ph-election-smartmatic/main/polars.png)
## Shameless Plug
[Visit my website](https://111110100.com)