# QA Results

> **Generated at:** 2026-08-16T22:29:50Z
>
> **Project:** SBM-AI-ASSISTANT
>
> **Overall status:** passed

## Tests and coverage

- Exit code: 0

```text
............................................................... [ 35%]
........................................................................ [ 76%]
..........................................                             [100%]
================================ tests coverage ================================
_______________ coverage: platform linux, python 3.11.16-final-0 _______________

Name                                                                    Stmts   Miss Branch BrPart  Cover   Missing
-------------------------------------------------------------------------------------------------------------------
backend/app/api/routes/contexts.py                                         51     19      0      0    63%   41-42, 53-54, 64-65, 99-102, 110-122
backend/app/api/routes/documentation.py                                    31     13      0      0    58%   53-59, 71-89
backend/app/config/settings.py                                             23      0      0      0   100%
backend/app/main.py                                                        23     23      0      0     0%   1-35
backend/app/schemas/contexts.py                                           160     11     50      9    90%   41, 48, 60-61, 72, 143, 165, 169, 182, 187, 299
backend/app/schemas/documentation.py                                       61      4     12      4    89%   33, 55, 106, 111
backend/app/services/chunk_service.py                                      10      0      4      1    93%   10->13
backend/app/services/contexts/__init__.py                                   0      0      0      0   100%
backend/app/services/contexts/context_export_service.py                   159     35     30      5    77%   73-76, 83, 92-101, 114-117, 138, 181-182, 187, 196-197, 207-208, 253-254, 284, 341->332, 343-350, 408-413, 447-452, 486-491
backend/app/services/contexts/context_index_service.py                    102      5     30      7    91%   139, 149->160, 191, 220, 263->298, 319, 327
backend/app/services/contexts/context_retrieval_service.py                 86      8     38      9    86%   127, 143, 168, 181->187, 188, 261, 264, 267, 311
backend/app/services/contexts/context_upgrade_service.py                  992    162    524    129    80%   131->138, 152, 154, 159, 161, 167, 194, 197, 199, 207, 209, 221, 223, 229-230, 232, 252-253, 269, 274-275, 282, 302-307, 314, 322, 338, 343-344, 346, 350, 373, 381, 396, 401, 405, 410, 414, 419, 426, 432, 442, 449, 468, 474, 500, 511, 529, 536, 558, 579, 591, 599, 606, 622, 655-666, 670->673, 686->679, 688, 694, 716, 721, 726, 728-736, 751->755, 756, 777, 780, 790, 798, 807, 816, 824, 828, 848, 892-893, 897, 931, 938, 949-954, 963, 968, 974, 994->996, 1017, 1029, 1044, 1068, 1074-1075, 1081, 1109, 1117, 1139, 1155, 1206->1208, 1226-1231, 1232->1222, 1251, 1270, 1291, 1297, 1305, 1311, 1325, 1330, 1343, 1415, 1450->1449, 1484, 1488, 1502, 1513, 1519, 1523, 1530, 1534, 1540, 1545, 1550, 1559, 1563, 1578, 1651, 1656, 1672, 1675->exit, 1696, 1712, 1764, 1776, 1793, 1822, 1837-1838, 1864, 1878, 1885, 1981-1982, 2018, 2035, 2059-2060, 2081, 2086, 2092-2093, 2097, 2105, 2114, 2120-2121
backend/app/services/contexts/contract_registry.py                         82      6     28      6    89%   276, 288, 326, 333, 335, 338
backend/app/services/contexts/file_discovery_service.py                   135     23     48     13    80%   179, 184, 199-200, 205, 220, 226-227, 232, 237, 279-280, 312-313, 318, 329, 342-343, 348, 374, 385, 438, 464
backend/app/services/contexts/markdown_chunk_service.py                    23      0     12      1    97%   26->exit
backend/app/services/contexts/models.py                                    28      0      0      0   100%
backend/app/services/contexts/zip_export_service.py                       125     11     30      4    89%   111-113, 127, 129, 170-173, 211, 507
backend/app/services/documentation/documentation_export_service.py        157     35     40     11    75%   88-91, 98, 108-126, 142-145, 186-187, 192, 198-202, 213-217, 238, 256, 263-264, 269, 271, 273, 285, 296-297, 334, 367, 388->375, 390-395, 512-517
backend/app/services/documentation/documentation_index_service.py          75     19     16      6    68%   88, 120-132, 147, 165-216, 226, 239, 246
backend/app/services/documentation/documentation_retrieval_service.py     123     11     62     13    87%   217, 265->273, 291, 371, 376, 381, 397, 402, 446, 520->557, 527, 532, 558
backend/app/services/documentation/documentation_upgrade_service.py       394     74    180     50    77%   104, 107, 114, 117, 126, 159, 169, 179, 182, 204, 206, 214-219, 222, 251, 274-278, 290, 296, 304, 312, 327, 380, 388, 402, 416-429, 447-467, 483, 493, 498, 518, 527, 530, 535, 546, 552, 563, 591, 594, 597, 603, 616, 635, 650, 656, 666, 681, 691, 699, 704, 840-844, 904, 922-923, 926, 976-977, 999, 1005, 1015-1016, 1022, 1034
backend/app/services/documentation/file_discovery_service.py              122     28     42     17    73%   44, 58, 63, 81-82, 87, 105, 111-112, 117, 124, 147-148, 167, 175-176, 180, 203, 212, 230-231, 236, 272, 288, 294-298, 369, 403
backend/app/services/documentation/markdown_chunk_service.py               24      0     12      1    97%   33->exit
backend/app/services/documentation/models.py                               20      0      0      0   100%
backend/app/services/documentation/zip_export_service.py                  108      8     26      5    90%   37, 41-42, 45, 57, 67, 189, 415
backend/app/services/embedding_service.py                                  12      5      2      0    50%   10, 14-17, 24
backend/app/services/project_registry.py                                   67      4     14      2    93%   133, 143-144, 149
backend/app/services/qdrant_service.py                                     91     46     30      3    43%   29, 53, 58->exit, 78-83, 97-99, 118-121, 149, 166-169, 182-185, 199-214, 218, 235-261, 271-303, 307-332, 336-380
-------------------------------------------------------------------------------------------------------------------
TOTAL                                                                    3284    550   1230    296    80%
Coverage XML written to file /workspace/coverage.xml
177 passed, 11 subtests passed in 5.32s
Coverage generado correctamente.
```

## SonarScanner

- Exit code: 0

```text
WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no specific platform was requested
22:28:05.836 INFO  Scanner configuration file: /opt/sonar-scanner/conf/sonar-scanner.properties
22:28:05.853 INFO  Project root configuration file: /usr/src/app/sonar-project.properties
22:28:05.979 INFO  SonarScanner CLI 8.0.1.6346
22:28:06.024 INFO  Linux 5.15.49-linuxkit-pr amd64
22:28:12.594 INFO  Communicating with SonarQube Community Build 26.7.0.124771
22:28:12.607 INFO  JRE provisioning: os[linux], arch[x86_64]
22:28:16.192 INFO  Starting SonarScanner Engine...
22:28:16.198 INFO  Java 21.0.9 Eclipse Adoptium (64-bit)
22:28:24.127 INFO  Load global settings
22:28:24.705 INFO  Load global settings (done) | time=585ms
22:28:24.727 INFO  Server id: 54000601-AZ-DAVF-MejkBZkEKtuI
22:28:24.835 INFO  Loading required plugins
22:28:24.838 INFO  Load plugins index
22:28:24.940 INFO  Load plugins index (done) | time=104ms
22:28:24.943 INFO  Load/download plugins
22:28:25.123 INFO  Load/download plugins (done) | time=179ms
22:28:27.465 INFO  Process project properties
22:28:27.542 INFO  Process project properties (done) | time=81ms
22:28:27.637 INFO  Project key: SBM-AI-ASSISTANT
22:28:27.639 INFO  Base dir: /usr/src/app
22:28:27.640 INFO  Working dir: /tmp/.scannerwork
22:28:27.694 INFO  Load project settings for component key: 'SBM-AI-ASSISTANT'
22:28:27.870 INFO  Load project settings for component key: 'SBM-AI-ASSISTANT' (done) | time=176ms
22:28:27.995 INFO  Load quality profiles
22:28:28.197 INFO  Load quality profiles (done) | time=202ms
22:28:28.503 INFO  Load active rules
22:28:30.986 INFO  Load active rules (done) | time=2458ms
22:28:31.081 INFO  Load analysis cache
22:28:31.227 INFO  Load analysis cache | time=146ms
22:28:32.322 INFO  Preprocessing files...
22:28:33.122 INFO  1 language detected in 48 preprocessed files (done) | time=787ms
22:28:33.146 INFO  11 files ignored because of inclusion/exclusion patterns
22:28:33.150 INFO  9 directories skipped because of exclusion patterns (content not counted)
22:28:33.154 INFO  7 files ignored because of scm ignore settings
22:28:33.168 INFO  Loading plugins for detected languages
22:28:33.171 INFO  Load/download plugins
22:28:33.225 INFO  Load/download plugins (done) | time=61ms
22:28:34.880 INFO  Load project repositories
22:28:35.530 INFO  Load project repositories (done) | time=658ms
22:28:35.771 INFO  Indexing files...
22:28:35.797 INFO  Project configuration:
22:28:35.805 INFO    Excluded sources: **/.venv/**, **/__pycache__/**, **/tests/**, backend/tests/**/*.py
22:28:35.807 INFO    Included tests: backend/tests/**/*.py
22:28:35.903 INFO  48 files indexed (done) | time=105ms
22:28:35.908 INFO  Quality profile for py: Sonar way
22:28:35.914 INFO  ------------- Run sensors on module SBM-AI-ASSISTANT
22:28:36.177 INFO  Load metrics repository
22:28:36.363 INFO  Load metrics repository (done) | time=187ms
22:28:39.404 INFO  Sensor IaC hadolint report Sensor [iac]
22:28:39.424 INFO  Sensor IaC hadolint report Sensor [iac] (done) | time=5ms
22:28:39.426 INFO  Sensor Java Config Sensor [iac]
22:28:40.889 INFO  There are no files to be analyzed for the Java language
22:28:40.904 INFO  Sensor Java Config Sensor [iac] (done) | time=1457ms
22:28:40.906 INFO  Sensor IaC Docker Sensor [iac]
22:28:40.950 INFO  There are no files to be analyzed for the Docker language
22:28:40.951 INFO  Sensor IaC Docker Sensor [iac] (done) | time=88ms
22:28:40.953 INFO  Sensor Python Sensor [python]
22:28:45.342 INFO  Starting global symbols computation
22:28:45.452 INFO  48 source files to be analyzed
22:28:55.592 INFO  24/48 files analyzed, current files: context_export_service.py, file_discovery_service.py, context_retrieval_service.py, ...
22:28:59.737 INFO  48/48 source files have been analyzed
22:28:59.740 INFO  Finished step global symbols computation in 14373ms
22:29:00.276 INFO  Starting rules execution
22:29:00.302 INFO  48 source files to be analyzed
22:29:10.348 INFO  5/48 files analyzed, current files: documentation_upgrade_service.py, file_discovery_service.py, documentation_export_service.py, ...
22:29:20.359 INFO  25/48 files analyzed, current files: context_export_service.py, context_retrieval_service.py, scheduler_service.py, ...
22:29:30.390 INFO  41/48 files analyzed, current files: context_upgrade_service.py, context_index_service.py, slack.py, ...
22:29:35.581 INFO  48/48 source files have been analyzed
22:29:35.584 INFO  Finished step rules execution in 35264ms
22:29:35.585 INFO  The Python analyzer was able to leverage cached data from previous analyses for 0 out of 48 files. These files were not parsed.
22:29:35.598 INFO  Sensor Python Sensor [python] (done) | time=54647ms
22:29:35.599 INFO  Sensor Cobertura Sensor for Python coverage [python]
22:29:36.718 INFO  Python test coverage
22:29:36.750 INFO  Parsing report '/usr/src/app/coverage.xml'
22:29:37.229 INFO  Sensor Cobertura Sensor for Python coverage [python] (done) | time=1627ms
22:29:37.232 INFO  Sensor PythonXUnitSensor [python]
22:29:38.037 INFO  Sensor PythonXUnitSensor [python] (done) | time=808ms
22:29:38.038 INFO  Sensor Python Dependency Sensor [python]
22:29:38.064 INFO  Sensor Python Dependency Sensor [python] (done) | time=27ms
22:29:38.065 INFO  Sensor TextAndSecretsSensor [text]
22:29:38.190 INFO  Available processors: 4
22:29:38.191 INFO  Using 4 threads for analysis.
22:29:40.847 INFO  Start fetching files for the text and secrets analysis
22:29:41.027 INFO  Using Git CLI to retrieve dirty files
22:29:41.209 WARN  Retrieving only language associated files, make sure to run the analysis inside a git repository to make use of inclusions specified via "sonar.text.inclusions"
22:29:41.214 INFO  Starting the text and secrets analysis
22:29:41.225 INFO  48 source files to be analyzed for the text and secrets analysis
22:29:41.913 INFO  48/48 source files have been analyzed for the text and secrets analysis
22:29:41.944 INFO  Sensor TextAndSecretsSensor [text] (done) | time=3874ms
22:29:41.970 INFO  ------------- Run sensors on project
22:29:42.610 INFO  Sensor IaC Project Sensor [iac]
22:29:42.623 INFO  Sensor IaC Project Sensor [iac] (done) | time=14ms
22:29:42.624 INFO  Sensor Zero Coverage Sensor
22:29:42.669 INFO  Sensor Zero Coverage Sensor (done) | time=45ms
22:29:42.671 INFO  ------------- Gather SCA dependencies on project
22:29:42.718 INFO  Dependency analysis skipped
22:29:42.877 INFO  CPD Executor 4 files had no CPD blocks
22:29:42.880 INFO  CPD Executor Calculating CPD for 39 files
22:29:43.214 INFO  CPD Executor CPD calculation finished (done) | time=331ms
22:29:43.288 INFO  SCM revision ID '82ff7f87bcb701c30b2e386c70a4bcbe92dab489'
22:29:44.181 INFO  Analysis report generated in 831ms, dir size=1.6 MB
22:29:44.610 INFO  Analysis report compressed in 424ms, zip size=660.6 kB
22:29:45.057 INFO  Analysis report uploaded in 445ms
22:29:45.077 INFO  ANALYSIS SUCCESSFUL, you can find the results at: http://host.docker.internal:9000/dashboard?id=SBM-AI-ASSISTANT
22:29:45.078 INFO  Note that you will be able to access the updated dashboard once the server has processed the submitted analysis report
22:29:45.079 INFO  More about the report processing at http://host.docker.internal:9000/api/ce/task?id=7a9a9d9c-9186-4238-b2b7-9e85b96bb093
22:29:45.228 INFO  Analysis total time: 1:19.801 s
22:29:45.245 INFO  SonarScanner Engine completed successfully
22:29:45.415 INFO  EXECUTION SUCCESS
22:29:45.458 INFO  Total time: 1:39.605s
Esperando procesamiento de SonarQube...
Quality Gate: OK
SonarQube Quality Gate aprobado.
```

## Evidence boundary

This file records only the output produced by the executed QA scripts.
It does not infer coverage, SonarQube status, deployments or quality gates not present in the logs.
