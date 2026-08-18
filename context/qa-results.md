# QA Results

> **Generated at:** 2026-08-18T17:32:10Z
>
> **Project:** SBM-AI-ASSISTANT
>
> **Overall status:** passed

## Tests and coverage

- Exit code: 0

```text
................................................................ [ 32%]
................................................................... [ 67%]
...............................................................        [100%]
================================ tests coverage ================================
_______________ coverage: platform linux, python 3.11.16-final-0 _______________

Name                                                                    Stmts   Miss Branch BrPart  Cover   Missing
-------------------------------------------------------------------------------------------------------------------
backend/app/api/routes/contexts.py                                         51     19      0      0    63%   41-42, 53-54, 64-65, 99-102, 110-122
backend/app/api/routes/documentation.py                                    31     13      0      0    58%   53-59, 71-89
backend/app/config/settings.py                                             23      0      0      0   100%
backend/app/main.py                                                        23     23      0      0     0%   1-35
backend/app/schemas/contexts.py                                           163     12     50     10    90%   45, 52, 64-65, 76, 151, 173, 180, 183, 189, 244, 316
backend/app/schemas/documentation.py                                       61      4     12      4    89%   33, 55, 106, 111
backend/app/services/chunk_service.py                                      10      0      4      1    93%   10->13
backend/app/services/contexts/__init__.py                                   0      0      0      0   100%
backend/app/services/contexts/context_export_service.py                   159     35     30      5    77%   73-76, 83, 92-101, 114-117, 138, 181-182, 187, 196-197, 207-208, 253-254, 284, 341->332, 343-350, 408-413, 447-452, 486-491
backend/app/services/contexts/context_index_service.py                    102      5     30      7    91%   139, 149->160, 191, 220, 263->298, 319, 327
backend/app/services/contexts/context_retrieval_service.py                 86      8     38      9    86%   127, 143, 168, 181->187, 188, 261, 264, 267, 311
backend/app/services/contexts/context_upgrade_service.py                 1103    181    594    137    80%   144->151, 165, 167, 172, 174, 180, 207, 210, 212, 220, 222, 234, 236, 242-243, 245, 265-266, 282, 287-288, 295, 319-324, 342, 349, 364, 369-370, 372, 376, 399, 407, 422, 427, 431, 436, 440, 445, 452, 458, 468, 475, 494, 500, 526, 537, 568, 581->586, 590-591, 598->602, 611, 632, 644, 652, 659, 675, 708-719, 723->726, 739->732, 741, 747, 769, 774, 779, 781-789, 804->808, 809, 830, 833, 843, 851, 860, 869, 877, 881, 901, 945-946, 950, 984, 991, 1006, 1017-1022, 1031, 1036, 1049, 1069->1071, 1092, 1104, 1119, 1143, 1149-1150, 1156, 1184, 1192, 1215, 1232, 1285->1287, 1305-1310, 1311->1301, 1330, 1349, 1370, 1376, 1384, 1390, 1404, 1409, 1422, 1436, 1503, 1613, 1648->1647, 1696, 1700, 1714, 1724, 1732, 1736, 1742, 1746, 1758, 1765, 1767, 1770, 1779, 1788, 1821-1826, 1830->1842, 1883, 1887, 1902, 1905->exit, 1934, 1950, 1954, 1958-1968, 2021, 2033, 2050, 2079, 2094-2095, 2121, 2135, 2142, 2238-2239, 2275, 2292, 2316-2317, 2338, 2343, 2349-2350, 2354, 2362, 2371, 2377-2378
backend/app/services/contexts/contract_registry.py                         82      6     28      6    89%   286, 298, 336, 343, 345, 348
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
TOTAL                                                                    3398    570   1300    305    80%
Coverage XML written to file /workspace/coverage.xml
194 passed, 15 subtests passed in 6.22s
Coverage generado correctamente.
```

## SonarScanner

- Exit code: 0

```text
WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no specific platform was requested
17:30:09.287 INFO  Scanner configuration file: /opt/sonar-scanner/conf/sonar-scanner.properties
17:30:09.303 INFO  Project root configuration file: /usr/src/app/sonar-project.properties
17:30:09.426 INFO  SonarScanner CLI 8.0.1.6346
17:30:09.472 INFO  Linux 5.15.49-linuxkit-pr amd64
17:30:16.401 INFO  Communicating with SonarQube Community Build 26.7.0.124771
17:30:16.407 INFO  JRE provisioning: os[linux], arch[x86_64]
17:30:20.417 INFO  Starting SonarScanner Engine...
17:30:20.419 INFO  Java 21.0.9 Eclipse Adoptium (64-bit)
17:30:29.857 INFO  Load global settings
17:30:30.432 INFO  Load global settings (done) | time=578ms
17:30:30.453 INFO  Server id: 54000601-AZ-DAVF-MejkBZkEKtuI
17:30:30.564 INFO  Loading required plugins
17:30:30.566 INFO  Load plugins index
17:30:30.689 INFO  Load plugins index (done) | time=121ms
17:30:30.691 INFO  Load/download plugins
17:30:30.851 INFO  Load/download plugins (done) | time=161ms
17:30:32.958 INFO  Process project properties
17:30:33.033 INFO  Process project properties (done) | time=76ms
17:30:33.131 INFO  Project key: SBM-AI-ASSISTANT
17:30:33.132 INFO  Base dir: /usr/src/app
17:30:33.133 INFO  Working dir: /tmp/.scannerwork
17:30:33.203 INFO  Load project settings for component key: 'SBM-AI-ASSISTANT'
17:30:33.437 INFO  Load project settings for component key: 'SBM-AI-ASSISTANT' (done) | time=236ms
17:30:33.582 INFO  Load quality profiles
17:30:33.824 INFO  Load quality profiles (done) | time=241ms
17:30:34.242 INFO  Load active rules
17:30:35.933 INFO  Load active rules (done) | time=1682ms
17:30:36.037 INFO  Load analysis cache
17:30:36.229 INFO  Load analysis cache | time=191ms
17:30:37.556 INFO  Preprocessing files...
17:30:38.192 INFO  1 language detected in 48 preprocessed files (done) | time=633ms
17:30:38.201 INFO  11 files ignored because of inclusion/exclusion patterns
17:30:38.203 INFO  9 directories skipped because of exclusion patterns (content not counted)
17:30:38.205 INFO  7 files ignored because of scm ignore settings
17:30:38.220 INFO  Loading plugins for detected languages
17:30:38.223 INFO  Load/download plugins
17:30:38.283 INFO  Load/download plugins (done) | time=62ms
17:30:40.564 INFO  Load project repositories
17:30:41.565 INFO  Load project repositories (done) | time=1010ms
17:30:41.912 INFO  Indexing files...
17:30:41.921 INFO  Project configuration:
17:30:41.939 INFO    Excluded sources: **/.venv/**, **/__pycache__/**, **/tests/**, backend/tests/**/*.py
17:30:41.942 INFO    Included tests: backend/tests/**/*.py
17:30:42.084 INFO  48 files indexed (done) | time=155ms
17:30:42.118 INFO  Quality profile for py: Sonar way
17:30:42.120 INFO  ------------- Run sensors on module SBM-AI-ASSISTANT
17:30:42.587 INFO  Load metrics repository
17:30:42.938 INFO  Load metrics repository (done) | time=369ms
17:30:46.486 INFO  Sensor IaC hadolint report Sensor [iac]
17:30:46.505 INFO  Sensor IaC hadolint report Sensor [iac] (done) | time=10ms
17:30:46.506 INFO  Sensor Java Config Sensor [iac]
17:30:48.162 INFO  There are no files to be analyzed for the Java language
17:30:48.170 INFO  Sensor Java Config Sensor [iac] (done) | time=1673ms
17:30:48.176 INFO  Sensor IaC Docker Sensor [iac]
17:30:48.299 INFO  There are no files to be analyzed for the Docker language
17:30:48.305 INFO  Sensor IaC Docker Sensor [iac] (done) | time=140ms
17:30:48.307 INFO  Sensor Python Sensor [python]
17:30:54.365 INFO  Starting global symbols computation
17:30:54.478 INFO  48 source files to be analyzed
17:31:04.676 INFO  17/48 files analyzed, current files: test_context_upgrade.py, contract_registry.py, html_parser.py, ...
17:31:09.400 INFO  48/48 source files have been analyzed
17:31:09.416 INFO  Finished step global symbols computation in 15041ms
17:31:10.065 INFO  Starting rules execution
17:31:10.077 INFO  48 source files to be analyzed
17:31:20.127 INFO  5/48 files analyzed, current files: documentation_upgrade_service.py, documentation_export_service.py, file_discovery_service.py, ...
17:31:30.264 INFO  23/48 files analyzed, current files: contract_registry.py, context_export_service.py, file_discovery_service.py, ...
17:31:40.317 INFO  39/48 files analyzed, current files: context_upgrade_service.py, documentation_retrieval_service.py, zip_export_service.py, ...
17:31:50.324 INFO  47/48 files analyzed, current file: context_upgrade_service.py
17:31:50.839 INFO  48/48 source files have been analyzed
17:31:50.840 INFO  Finished step rules execution in 40768ms
17:31:50.841 INFO  The Python analyzer was able to leverage cached data from previous analyses for 0 out of 48 files. These files were not parsed.
17:31:50.873 INFO  Sensor Python Sensor [python] (done) | time=62573ms
17:31:50.875 INFO  Sensor Cobertura Sensor for Python coverage [python]
17:31:51.962 INFO  Python test coverage
17:31:51.988 INFO  Parsing report '/usr/src/app/coverage.xml'
17:31:52.477 INFO  Sensor Cobertura Sensor for Python coverage [python] (done) | time=1602ms
17:31:52.482 INFO  Sensor PythonXUnitSensor [python]
17:31:53.383 INFO  Sensor PythonXUnitSensor [python] (done) | time=905ms
17:31:53.384 INFO  Sensor Python Dependency Sensor [python]
17:31:53.428 INFO  Sensor Python Dependency Sensor [python] (done) | time=43ms
17:31:53.430 INFO  Sensor TextAndSecretsSensor [text]
17:31:53.574 INFO  Available processors: 6
17:31:53.576 INFO  Using 6 threads for analysis.
17:31:55.812 INFO  Start fetching files for the text and secrets analysis
17:31:55.996 INFO  Using Git CLI to retrieve dirty files
17:31:56.140 WARN  Retrieving only language associated files, make sure to run the analysis inside a git repository to make use of inclusions specified via "sonar.text.inclusions"
17:31:56.151 INFO  Starting the text and secrets analysis
17:31:56.162 INFO  48 source files to be analyzed for the text and secrets analysis
17:31:56.997 INFO  48/48 source files have been analyzed for the text and secrets analysis
17:31:57.017 INFO  Sensor TextAndSecretsSensor [text] (done) | time=3588ms
17:31:57.046 INFO  ------------- Run sensors on project
17:31:57.704 INFO  Sensor IaC Project Sensor [iac]
17:31:57.717 INFO  Sensor IaC Project Sensor [iac] (done) | time=20ms
17:31:57.718 INFO  Sensor Zero Coverage Sensor
17:31:57.767 INFO  Sensor Zero Coverage Sensor (done) | time=50ms
17:31:57.770 INFO  ------------- Gather SCA dependencies on project
17:31:57.813 INFO  Dependency analysis skipped
17:31:57.864 INFO  SCM Publisher SCM provider for this project is: git
17:31:57.873 INFO  SCM Publisher 5 source files to be analyzed
17:31:58.000 WARN  Thread[#62,ForkJoinPool.commonPool-worker-1,5,main]: got smaller file timestamp on /usr/src/app (/host_mark/Users), /usr/src/app/.git: 2026-08-18T17:31:57Z < 2026-08-18T17:31:57.989184008Z. Aborting measurement at resolution PT0.010815992S.
17:31:59.730 INFO  SCM Publisher 0/5 source files have been analyzed (done) | time=1831ms
17:31:59.747 WARN  Missing blame information for the following files:
17:31:59.749 WARN    * backend/tests/test_context_upgrade.py
17:31:59.751 WARN    * backend/app/schemas/contexts.py
17:31:59.752 WARN    * backend/app/services/contexts/contract_registry.py
17:31:59.752 WARN    * backend/app/services/contexts/context_upgrade_service.py
17:31:59.753 WARN    * backend/tests/test_context_export.py
17:31:59.756 WARN  This may lead to missing/broken features in SonarQube
17:31:59.881 INFO  CPD Executor 4 files had no CPD blocks
17:31:59.882 INFO  CPD Executor Calculating CPD for 39 files
17:32:00.143 INFO  CPD Executor CPD calculation finished (done) | time=262ms
17:32:00.204 INFO  SCM revision ID '738c4802c6400a1aa04f43563fd353aaf9765713'
17:32:01.030 INFO  Analysis report generated in 811ms, dir size=1.7 MB
17:32:01.418 INFO  Analysis report compressed in 378ms, zip size=685.0 kB
17:32:01.945 INFO  Analysis report uploaded in 532ms
17:32:01.964 INFO  ANALYSIS SUCCESSFUL, you can find the results at: http://host.docker.internal:9000/dashboard?id=SBM-AI-ASSISTANT
17:32:01.965 INFO  Note that you will be able to access the updated dashboard once the server has processed the submitted analysis report
17:32:01.966 INFO  More about the report processing at http://host.docker.internal:9000/api/ce/task?id=87edcb3e-38e6-4c3f-a06f-bab7a0cf14fd
17:32:02.066 INFO  Analysis total time: 1:30.996 s
17:32:02.069 INFO  SonarScanner Engine completed successfully
17:32:02.199 INFO  EXECUTION SUCCESS
17:32:02.268 INFO  Total time: 1:52.947s
Esperando procesamiento de SonarQube...
Quality Gate: OK
SonarQube Quality Gate aprobado.
```

## Evidence boundary

This file records only the output produced by the executed QA scripts.
It does not infer coverage, SonarQube status, deployments or quality gates not present in the logs.
