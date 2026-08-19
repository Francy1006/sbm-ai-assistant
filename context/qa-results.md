# QA Results

> **Generated at:** 2026-08-19T19:45:06Z
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
194 passed, 15 subtests passed in 5.70s
Coverage generado correctamente.
```

## SonarScanner

- Exit code: 0

```text
WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no specific platform was requested
19:43:08.929 INFO  Scanner configuration file: /opt/sonar-scanner/conf/sonar-scanner.properties
19:43:08.946 INFO  Project root configuration file: /usr/src/app/sonar-project.properties
19:43:09.041 INFO  SonarScanner CLI 8.0.1.6346
19:43:09.075 INFO  Linux 5.15.49-linuxkit-pr amd64
19:43:16.856 INFO  Communicating with SonarQube Community Build 26.7.0.124771
19:43:16.863 INFO  JRE provisioning: os[linux], arch[x86_64]
19:43:21.284 INFO  Starting SonarScanner Engine...
19:43:21.287 INFO  Java 21.0.9 Eclipse Adoptium (64-bit)
19:43:30.688 INFO  Load global settings
19:43:31.345 INFO  Load global settings (done) | time=665ms
19:43:31.371 INFO  Server id: 54000601-AZ-DAVF-MejkBZkEKtuI
19:43:31.452 INFO  Loading required plugins
19:43:31.453 INFO  Load plugins index
19:43:31.623 INFO  Load plugins index (done) | time=169ms
19:43:31.627 INFO  Load/download plugins
19:43:31.840 INFO  Load/download plugins (done) | time=209ms
19:43:33.763 INFO  Process project properties
19:43:33.899 INFO  Process project properties (done) | time=139ms
19:43:34.033 INFO  Project key: SBM-AI-ASSISTANT
19:43:34.034 INFO  Base dir: /usr/src/app
19:43:34.035 INFO  Working dir: /tmp/.scannerwork
19:43:34.099 INFO  Load project settings for component key: 'SBM-AI-ASSISTANT'
19:43:34.276 INFO  Load project settings for component key: 'SBM-AI-ASSISTANT' (done) | time=173ms
19:43:34.430 INFO  Load quality profiles
19:43:34.840 INFO  Load quality profiles (done) | time=410ms
19:43:35.256 INFO  Load active rules
19:43:38.500 INFO  Load active rules (done) | time=3235ms
19:43:38.592 INFO  Load analysis cache
19:43:38.765 INFO  Load analysis cache | time=173ms
19:43:40.034 INFO  Preprocessing files...
19:43:40.519 INFO  1 language detected in 48 preprocessed files (done) | time=498ms
19:43:40.521 INFO  11 files ignored because of inclusion/exclusion patterns
19:43:40.523 INFO  9 directories skipped because of exclusion patterns (content not counted)
19:43:40.524 INFO  7 files ignored because of scm ignore settings
19:43:40.544 INFO  Loading plugins for detected languages
19:43:40.546 INFO  Load/download plugins
19:43:40.589 INFO  Load/download plugins (done) | time=42ms
19:43:41.333 INFO  Load project repositories
19:43:42.262 INFO  Load project repositories (done) | time=910ms
19:43:42.699 INFO  Indexing files...
19:43:42.708 INFO  Project configuration:
19:43:42.721 INFO    Excluded sources: **/.venv/**, **/__pycache__/**, **/tests/**, backend/tests/**/*.py
19:43:42.725 INFO    Included tests: backend/tests/**/*.py
19:43:42.874 INFO  48 files indexed (done) | time=160ms
19:43:42.883 INFO  Quality profile for py: Sonar way
19:43:42.886 INFO  ------------- Run sensors on module SBM-AI-ASSISTANT
19:43:43.225 INFO  Load metrics repository
19:43:43.410 INFO  Load metrics repository (done) | time=187ms
19:43:46.219 INFO  Sensor IaC hadolint report Sensor [iac]
19:43:46.227 INFO  Sensor IaC hadolint report Sensor [iac] (done) | time=9ms
19:43:46.229 INFO  Sensor Java Config Sensor [iac]
19:43:47.180 INFO  There are no files to be analyzed for the Java language
19:43:47.187 INFO  Sensor Java Config Sensor [iac] (done) | time=955ms
19:43:47.189 INFO  Sensor IaC Docker Sensor [iac]
19:43:47.200 INFO  There are no files to be analyzed for the Docker language
19:43:47.203 INFO  Sensor IaC Docker Sensor [iac] (done) | time=22ms
19:43:47.204 INFO  Sensor Python Sensor [python]
19:43:53.159 INFO  Starting global symbols computation
19:43:53.310 INFO  48 source files to be analyzed
19:44:03.684 INFO  25/48 files analyzed, current files: context_export_service.py, file_discovery_service.py, context_retrieval_service.py, ...
19:44:09.527 INFO  48/48 source files have been analyzed
19:44:09.547 INFO  Finished step global symbols computation in 16357ms
19:44:10.160 INFO  Starting rules execution
19:44:10.172 INFO  48 source files to be analyzed
19:44:20.390 INFO  7/48 files analyzed, current files: documentation_upgrade_service.py, documentation_export_service.py, test_context_upgrade.py, ...
19:44:30.459 INFO  34/48 files analyzed, current files: documentation_index_service.py, context_upgrade_service.py, zip_export_service.py, ...
19:44:40.453 INFO  47/48 files analyzed, current file: context_upgrade_service.py
19:44:47.503 INFO  48/48 source files have been analyzed
19:44:47.507 INFO  Finished step rules execution in 37312ms
19:44:47.514 INFO  The Python analyzer was able to leverage cached data from previous analyses for 0 out of 48 files. These files were not parsed.
19:44:47.569 INFO  Sensor Python Sensor [python] (done) | time=60375ms
19:44:47.575 INFO  Sensor Cobertura Sensor for Python coverage [python]
19:44:49.160 INFO  Python test coverage
19:44:49.211 INFO  Parsing report '/usr/src/app/coverage.xml'
19:44:49.829 INFO  Sensor Cobertura Sensor for Python coverage [python] (done) | time=2255ms
19:44:49.831 INFO  Sensor PythonXUnitSensor [python]
19:44:50.859 INFO  Sensor PythonXUnitSensor [python] (done) | time=1019ms
19:44:50.865 INFO  Sensor Python Dependency Sensor [python]
19:44:50.921 INFO  Sensor Python Dependency Sensor [python] (done) | time=71ms
19:44:50.925 INFO  Sensor TextAndSecretsSensor [text]
19:44:51.721 INFO  Available processors: 6
19:44:51.740 INFO  Using 6 threads for analysis.
19:44:54.109 INFO  Start fetching files for the text and secrets analysis
19:44:54.317 INFO  Using Git CLI to retrieve dirty files
19:44:54.416 WARN  Retrieving only language associated files, make sure to run the analysis inside a git repository to make use of inclusions specified via "sonar.text.inclusions"
19:44:54.421 INFO  Starting the text and secrets analysis
19:44:54.430 INFO  48 source files to be analyzed for the text and secrets analysis
19:44:55.229 INFO  48/48 source files have been analyzed for the text and secrets analysis
19:44:55.251 INFO  Sensor TextAndSecretsSensor [text] (done) | time=4329ms
19:44:55.293 INFO  ------------- Run sensors on project
19:44:55.904 INFO  Sensor IaC Project Sensor [iac]
19:44:55.913 INFO  Sensor IaC Project Sensor [iac] (done) | time=10ms
19:44:55.915 INFO  Sensor Zero Coverage Sensor
19:44:55.983 INFO  Sensor Zero Coverage Sensor (done) | time=68ms
19:44:55.984 INFO  ------------- Gather SCA dependencies on project
19:44:56.024 INFO  Dependency analysis skipped
19:44:56.187 INFO  CPD Executor 4 files had no CPD blocks
19:44:56.191 INFO  CPD Executor Calculating CPD for 39 files
19:44:56.383 INFO  CPD Executor CPD calculation finished (done) | time=193ms
19:44:56.445 INFO  SCM revision ID '92a34c5d97c00a3b608fb133a43c81e0346728f3'
19:44:57.180 INFO  Analysis report generated in 728ms, dir size=1.7 MB
19:44:57.604 INFO  Analysis report compressed in 421ms, zip size=684.7 kB
19:44:58.189 INFO  Analysis report uploaded in 584ms
19:44:58.206 INFO  ANALYSIS SUCCESSFUL, you can find the results at: http://host.docker.internal:9000/dashboard?id=SBM-AI-ASSISTANT
19:44:58.210 INFO  Note that you will be able to access the updated dashboard once the server has processed the submitted analysis report
19:44:58.212 INFO  More about the report processing at http://host.docker.internal:9000/api/ce/task?id=34020d88-9eb8-4131-b9c8-f06e3f34e7a5
19:44:58.327 INFO  Analysis total time: 1:26.254 s
19:44:58.338 INFO  SonarScanner Engine completed successfully
19:44:58.493 INFO  EXECUTION SUCCESS
19:44:58.568 INFO  Total time: 1:49.599s
Esperando procesamiento de SonarQube...
Quality Gate: OK
SonarQube Quality Gate aprobado.
```

## Evidence boundary

This file records only the output produced by the executed QA scripts.
It does not infer coverage, SonarQube status, deployments or quality gates not present in the logs.
