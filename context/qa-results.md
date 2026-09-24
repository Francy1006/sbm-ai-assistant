# QA Results

> **Generated at:** 2026-09-24T15:48:12Z
>
> **Project:** SBM-AI-ASSISTANT
>
> **Overall status:** passed

## Tests and coverage

- Exit code: 0

```text
 Container sbm-ai-assistant-backend-run-7df6cb45f9f4 Creating
 Container sbm-ai-assistant-backend-run-7df6cb45f9f4 Created
................................................................ [ 32%]
................................................................... [ 67%]
...............................................................        [100%]
=============================== warnings summary ===============================
../usr/local/lib/python3.11/site-packages/starlette/testclient.py:53
  /usr/local/lib/python3.11/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
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
194 passed, 1 warning, 15 subtests passed in 34.89s
Coverage generado correctamente.
```

## SonarScanner

- Exit code: 0

```text
15:46:09.721 INFO  Scanner configuration file: /opt/sonar-scanner/conf/sonar-scanner.properties
15:46:09.731 INFO  Project root configuration file: /usr/src/app/sonar-project.properties
15:46:09.766 INFO  SonarScanner CLI 8.1.0.6389
15:46:09.780 INFO  Linux 6.18.33.2-microsoft-standard-WSL2 amd64
15:46:17.083 INFO  Communicating with SonarQube Community Build 26.7.0.124771
15:46:17.085 INFO  JRE provisioning: os[linux], arch[x86_64]
15:46:29.013 INFO  Starting SonarScanner Engine...
15:46:29.023 INFO  Java 21.0.9 Eclipse Adoptium (64-bit)
15:46:39.297 INFO  Load global settings
15:46:39.966 INFO  Load global settings (done) | time=662ms
15:46:39.985 INFO  Server id: 54000601-AZ-DAVF-MejkBZkEKtuI
15:46:40.014 INFO  Loading required plugins
15:46:40.015 INFO  Load plugins index
15:46:40.064 INFO  Load plugins index (done) | time=49ms
15:46:40.066 INFO  Load/download plugins
15:46:40.366 INFO  Load/download plugins (done) | time=300ms
15:46:41.825 INFO  Process project properties
15:46:41.925 INFO  Process project properties (done) | time=101ms
15:46:41.977 INFO  Project key: SBM-AI-ASSISTANT
15:46:41.978 INFO  Base dir: /usr/src/app
15:46:41.979 INFO  Working dir: /usr/src/app/.scannerwork
15:46:42.022 INFO  Load project settings for component key: 'SBM-AI-ASSISTANT'
15:46:42.062 INFO  Load project settings for component key: 'SBM-AI-ASSISTANT' (done) | time=40ms
15:46:42.117 INFO  Load quality profiles
15:46:42.257 INFO  Load quality profiles (done) | time=140ms
15:46:42.436 INFO  Load active rules
15:46:43.127 INFO  Load active rules (done) | time=690ms
15:46:43.140 INFO  Load analysis cache
15:46:43.278 INFO  Load analysis cache | time=138ms
15:46:43.798 INFO  Preprocessing files...
15:46:44.991 INFO  1 language detected in 48 preprocessed files (done) | time=1192ms
15:46:44.992 INFO  5 files ignored because of inclusion/exclusion patterns
15:46:44.993 INFO  9 directories skipped because of exclusion patterns (content not counted)
15:46:44.994 INFO  0 files ignored because of scm ignore settings
15:46:45.003 INFO  Loading plugins for detected languages
15:46:45.004 INFO  Load/download plugins
15:46:45.177 INFO  Load/download plugins (done) | time=173ms
15:46:46.195 INFO  Load project repositories
15:46:46.602 INFO  Load project repositories (done) | time=407ms
15:46:46.647 INFO  Indexing files...
15:46:46.651 INFO  Project configuration:
15:46:46.652 INFO    Excluded sources: **/.venv/**, **/__pycache__/**, **/tests/**, backend/tests/**/*.py
15:46:46.653 INFO    Included tests: backend/tests/**/*.py
15:46:47.020 INFO  48 files indexed (done) | time=372ms
15:46:47.023 INFO  Quality profile for py: Sonar way
15:46:47.024 INFO  ------------- Run sensors on module SBM-AI-ASSISTANT
15:46:47.175 INFO  Load metrics repository
15:46:47.228 INFO  Load metrics repository (done) | time=53ms
15:46:49.681 INFO  Sensor IaC hadolint report Sensor [iac]
15:46:49.683 INFO  Sensor IaC hadolint report Sensor [iac] (done) | time=3ms
15:46:49.684 INFO  Sensor Java Config Sensor [iac]
15:46:50.731 INFO  There are no files to be analyzed for the Java language
15:46:50.732 INFO  Sensor Java Config Sensor [iac] (done) | time=1047ms
15:46:50.732 INFO  Sensor IaC Docker Sensor [iac]
15:46:50.737 INFO  There are no files to be analyzed for the Docker language
15:46:50.738 INFO  Sensor IaC Docker Sensor [iac] (done) | time=5ms
15:46:50.739 INFO  Sensor Python Sensor [python]
15:46:58.021 INFO  Starting global symbols computation
15:46:58.026 INFO  48 source files to be analyzed
15:47:01.447 INFO  48/48 source files have been analyzed
15:47:01.451 INFO  Finished step global symbols computation in 3425ms
15:47:01.748 INFO  Starting rules execution
15:47:01.749 INFO  48 source files to be analyzed
15:47:11.751 INFO  47/48 files analyzed, current file: context_upgrade_service.py
15:47:12.910 INFO  48/48 source files have been analyzed
15:47:12.911 INFO  Finished step rules execution in 11161ms
15:47:12.912 INFO  The Python analyzer was able to leverage cached data from previous analyses for 0 out of 48 files. These files were not parsed.
15:47:12.925 INFO  Sensor Python Sensor [python] (done) | time=22187ms
15:47:12.925 INFO  Sensor Cobertura Sensor for Python coverage [python]
15:47:16.506 INFO  Python test coverage
15:47:16.518 INFO  Parsing report '/usr/src/app/coverage.xml'
15:47:17.248 INFO  Sensor Cobertura Sensor for Python coverage [python] (done) | time=4323ms
15:47:17.249 INFO  Sensor PythonXUnitSensor [python]
15:47:21.114 INFO  Sensor PythonXUnitSensor [python] (done) | time=3865ms
15:47:21.115 INFO  Sensor Python Dependency Sensor [python]
15:47:21.135 INFO  Sensor Python Dependency Sensor [python] (done) | time=20ms
15:47:21.135 INFO  Sensor TextAndSecretsSensor [text]
15:47:21.220 INFO  Available processors: 8
15:47:21.221 INFO  Using 8 threads for analysis.
15:47:22.564 INFO  Start fetching files for the text and secrets analysis
15:47:22.617 INFO  Using JGit to retrieve dirty files
15:47:23.279 WARN  Thread[#50,ForkJoinPool.commonPool-worker-1,5,main]: got smaller file timestamp on /usr/src/app (F:\), /usr/src/app/.git: 2026-09-24T15:47:23Z < 2026-09-24T15:47:23.2463982Z. Aborting measurement at resolution PT0.7536018S.
15:47:24.282 INFO  Retrieving language associated files and files included via "sonar.text.inclusions" that are tracked by git
15:47:24.283 INFO  Starting the text and secrets analysis
15:47:24.290 INFO  48 source files to be analyzed for the text and secrets analysis
15:47:24.583 INFO  48/48 source files have been analyzed for the text and secrets analysis
15:47:24.589 INFO  Sensor TextAndSecretsSensor [text] (done) | time=3452ms
15:47:24.599 INFO  ------------- Run sensors on project
15:47:25.320 INFO  Sensor IaC Project Sensor [iac]
15:47:25.322 INFO  Sensor IaC Project Sensor [iac] (done) | time=1ms
15:47:25.322 INFO  Sensor Zero Coverage Sensor
15:47:25.445 INFO  Sensor Zero Coverage Sensor (done) | time=123ms
15:47:25.446 INFO  ------------- Gather SCA dependencies on project
15:47:25.465 INFO  Dependency analysis skipped
15:47:25.722 INFO  CPD Executor 4 files had no CPD blocks
15:47:25.723 INFO  CPD Executor Calculating CPD for 39 files
15:47:25.979 INFO  CPD Executor CPD calculation finished (done) | time=256ms
15:47:26.068 INFO  SCM revision ID 'e8ad5dce617a7123cc984048de064072f29b0b09'
15:47:28.370 INFO  Analysis report generated in 1424ms, dir size=1.7 MB
15:48:05.979 INFO  Analysis report compressed in 37601ms, zip size=689.7 kB
15:48:06.388 INFO  Analysis report uploaded in 409ms
15:48:06.399 INFO  ANALYSIS SUCCESSFUL, you can find the results at: http://host.docker.internal:9000/dashboard?id=SBM-AI-ASSISTANT
15:48:06.400 INFO  Note that you will be able to access the updated dashboard once the server has processed the submitted analysis report
15:48:06.401 INFO  More about the report processing at http://host.docker.internal:9000/api/ce/task?id=72bd0da1-66bd-4d63-bb9c-20b9e653f560
15:48:08.291 INFO  Analysis total time: 1:27.600 s
15:48:08.301 INFO  SonarScanner Engine completed successfully
15:48:08.505 INFO  EXECUTION SUCCESS
15:48:08.507 INFO  Total time: 1:58.790s
Esperando procesamiento de SonarQube...
Quality Gate: OK
SonarQube Quality Gate aprobado.
```

## Evidence boundary

This file records only the output produced by the executed QA scripts.
It does not infer coverage, SonarQube status, deployments or quality gates not present in the logs.
