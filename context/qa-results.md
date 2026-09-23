# QA Results

> **Generated at:** 2026-09-23T20:47:10Z
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
194 passed, 1 warning, 15 subtests passed in 10.11s
Coverage generado correctamente.
```

## SonarScanner

- Exit code: 0

```text
20:45:42.393 INFO  Scanner configuration file: /opt/sonar-scanner/conf/sonar-scanner.properties
20:45:42.399 INFO  Project root configuration file: /usr/src/app/sonar-project.properties
20:45:42.416 INFO  SonarScanner CLI 8.1.0.6389
20:45:42.430 INFO  Linux 5.15.49-linuxkit-pr aarch64
20:45:49.860 INFO  Communicating with SonarQube Community Build 26.7.0.124771
20:45:49.900 INFO  JRE provisioning: os[linux], arch[aarch64]
20:45:54.492 INFO  Starting SonarScanner Engine...
20:45:54.499 INFO  Java 21.0.9 Eclipse Adoptium (64-bit)
20:46:01.085 INFO  Load global settings
20:46:01.609 INFO  Load global settings (done) | time=525ms
20:46:01.612 INFO  Server id: 54000601-AZ-DAVF-MejkBZkEKtuI
20:46:01.647 INFO  Loading required plugins
20:46:01.648 INFO  Load plugins index
20:46:01.868 INFO  Load plugins index (done) | time=219ms
20:46:01.870 INFO  Load/download plugins
20:46:02.020 INFO  Load/download plugins (done) | time=152ms
20:46:03.337 INFO  Process project properties
20:46:03.524 INFO  Process project properties (done) | time=218ms
20:46:03.625 INFO  Project key: SBM-AI-ASSISTANT
20:46:03.627 INFO  Base dir: /usr/src/app
20:46:03.629 INFO  Working dir: /usr/src/app/.scannerwork
20:46:03.689 INFO  Load project settings for component key: 'SBM-AI-ASSISTANT'
20:46:04.062 INFO  Load project settings for component key: 'SBM-AI-ASSISTANT' (done) | time=361ms
20:46:04.086 INFO  Load quality profiles
20:46:04.642 INFO  Load quality profiles (done) | time=555ms
20:46:04.741 INFO  Load active rules
20:46:06.728 INFO  Load active rules (done) | time=1947ms
20:46:06.773 INFO  Load analysis cache
20:46:07.556 INFO  Load analysis cache | time=766ms
20:46:08.862 INFO  Preprocessing files...
20:46:09.504 INFO  1 language detected in 48 preprocessed files (done) | time=644ms
20:46:09.533 INFO  11 files ignored because of inclusion/exclusion patterns
20:46:09.543 INFO  9 directories skipped because of exclusion patterns (content not counted)
20:46:09.567 INFO  7 files ignored because of scm ignore settings
20:46:09.568 INFO  Loading plugins for detected languages
20:46:09.575 INFO  Load/download plugins
20:46:09.796 INFO  Load/download plugins (done) | time=274ms
20:46:11.335 INFO  Load project repositories
20:46:11.836 INFO  Load project repositories (done) | time=525ms
20:46:11.881 INFO  Indexing files...
20:46:11.884 INFO  Project configuration:
20:46:11.900 INFO    Excluded sources: **/.venv/**, **/__pycache__/**, **/tests/**, backend/tests/**/*.py
20:46:11.901 INFO    Included tests: backend/tests/**/*.py
20:46:11.958 INFO  48 files indexed (done) | time=74ms
20:46:11.961 INFO  Quality profile for py: Sonar way
20:46:11.963 INFO  ------------- Run sensors on module SBM-AI-ASSISTANT
20:46:12.118 INFO  Load metrics repository
20:46:12.402 INFO  Load metrics repository (done) | time=278ms
20:46:14.577 INFO  Sensor IaC hadolint report Sensor [iac]
20:46:14.585 INFO  Sensor IaC hadolint report Sensor [iac] (done) | time=2ms
20:46:14.586 INFO  Sensor Java Config Sensor [iac]
20:46:14.873 INFO  There are no files to be analyzed for the Java language
20:46:14.879 INFO  Sensor Java Config Sensor [iac] (done) | time=294ms
20:46:14.880 INFO  Sensor IaC Docker Sensor [iac]
20:46:14.881 INFO  There are no files to be analyzed for the Docker language
20:46:14.881 INFO  Sensor IaC Docker Sensor [iac] (done) | time=2ms
20:46:14.881 INFO  Sensor Python Sensor [python]
20:46:20.104 INFO  Starting global symbols computation
20:46:20.115 INFO  48 source files to be analyzed
20:46:22.554 INFO  48/48 source files have been analyzed
20:46:22.557 INFO  Finished step global symbols computation in 2462ms
20:46:22.776 INFO  Starting rules execution
20:46:22.784 INFO  48 source files to be analyzed
20:46:29.397 INFO  48/48 source files have been analyzed
20:46:29.410 INFO  Finished step rules execution in 6606ms
20:46:29.413 INFO  The Python analyzer was able to leverage cached data from previous analyses for 0 out of 48 files. These files were not parsed.
20:46:29.415 INFO  Sensor Python Sensor [python] (done) | time=14521ms
20:46:29.416 INFO  Sensor Cobertura Sensor for Python coverage [python]
20:46:30.768 INFO  Python test coverage
20:46:30.781 INFO  Parsing report '/usr/src/app/coverage.xml'
20:46:31.023 INFO  Sensor Cobertura Sensor for Python coverage [python] (done) | time=1628ms
20:46:31.024 INFO  Sensor PythonXUnitSensor [python]
20:46:31.927 INFO  Sensor PythonXUnitSensor [python] (done) | time=888ms
20:46:31.933 INFO  Sensor Python Dependency Sensor [python]
20:46:31.953 INFO  Sensor Python Dependency Sensor [python] (done) | time=39ms
20:46:31.955 INFO  Sensor TextAndSecretsSensor [text]
20:46:32.023 INFO  Available processors: 6
20:46:32.023 INFO  Using 6 threads for analysis.
20:46:32.312 INFO  Start fetching files for the text and secrets analysis
20:46:32.351 INFO  Using JGit to retrieve dirty files
20:46:32.676 WARN  Thread[#44,ForkJoinPool.commonPool-worker-1,5,main]: got smaller file timestamp on /usr/src/app (/host_mark/Users), /usr/src/app/.git: 2026-09-23T20:46:32Z < 2026-09-23T20:46:32.654970763Z. Aborting measurement at resolution PT0.345029237S.
20:46:32.785 INFO  Retrieving language associated files and files included via "sonar.text.inclusions" that are tracked by git
20:46:32.788 INFO  Starting the text and secrets analysis
20:46:32.791 INFO  48 source files to be analyzed for the text and secrets analysis
20:46:33.094 INFO  48/48 source files have been analyzed for the text and secrets analysis
20:46:33.102 INFO  Sensor TextAndSecretsSensor [text] (done) | time=1145ms
20:46:33.119 INFO  ------------- Run sensors on project
20:46:34.019 INFO  Sensor IaC Project Sensor [iac]
20:46:34.023 INFO  Sensor IaC Project Sensor [iac] (done) | time=9ms
20:46:34.025 INFO  Sensor Zero Coverage Sensor
20:46:34.076 INFO  Sensor Zero Coverage Sensor (done) | time=53ms
20:46:34.077 INFO  ------------- Gather SCA dependencies on project
20:46:34.099 INFO  Dependency analysis skipped
20:46:34.263 INFO  CPD Executor 4 files had no CPD blocks
20:46:34.265 INFO  CPD Executor Calculating CPD for 39 files
20:46:34.410 INFO  CPD Executor CPD calculation finished (done) | time=147ms
20:46:34.442 INFO  SCM revision ID '75c1b645d4ca2ad2db350f87a3ddf207ff74b0de'
20:46:36.823 INFO  Analysis report generated in 2255ms, dir size=1.7 MB
20:46:40.937 INFO  Analysis report compressed in 4101ms, zip size=685.1 kB
20:46:42.661 INFO  Analysis report uploaded in 1720ms
20:46:42.683 INFO  ANALYSIS SUCCESSFUL, you can find the results at: http://host.docker.internal:9000/dashboard?id=SBM-AI-ASSISTANT
20:46:42.683 INFO  Note that you will be able to access the updated dashboard once the server has processed the submitted analysis report
20:46:42.684 INFO  More about the report processing at http://host.docker.internal:9000/api/ce/task?id=1ea23b41-1b99-4f4c-a278-f4339789dd05
20:46:43.078 INFO  Analysis total time: 40.960 s
20:46:43.130 INFO  SonarScanner Engine completed successfully
20:46:44.115 INFO  EXECUTION SUCCESS
20:46:44.268 INFO  Total time: 1:01.740s
Esperando procesamiento de SonarQube...
Quality Gate: OK
SonarQube Quality Gate aprobado.
```

## Evidence boundary

This file records only the output produced by the executed QA scripts.
It does not infer coverage, SonarQube status, deployments or quality gates not present in the logs.
