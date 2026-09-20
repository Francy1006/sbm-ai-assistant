# QA Results

> **Generated at:** 2026-09-20T02:03:11Z
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

tests/test_context_upgrade.py::ContextUpgradeTests::test_global_qa_cannot_remove_another_project
  /usr/local/lib/python3.11/site-packages/qdrant_client/qdrant_remote.py:292: UserWarning: Failed to obtain server version. Unable to check client-server compatibility. Set check_compatibility=False to skip version check.
    show_warning(

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
194 passed, 2 warnings, 15 subtests passed in 9.86s
Coverage generado correctamente.
```

## SonarScanner

- Exit code: 0

```text
WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no specific platform was requested
02:00:58.824 INFO  Scanner configuration file: /opt/sonar-scanner/conf/sonar-scanner.properties
02:00:58.844 INFO  Project root configuration file: /usr/src/app/sonar-project.properties
02:00:58.987 INFO  SonarScanner CLI 8.1.0.6389
02:00:59.057 INFO  Linux 5.15.49-linuxkit-pr amd64
02:01:07.900 INFO  Communicating with SonarQube Community Build 26.7.0.124771
02:01:07.908 INFO  JRE provisioning: os[linux], arch[x86_64]
02:01:13.544 INFO  Starting SonarScanner Engine...
02:01:13.547 INFO  Java 21.0.9 Eclipse Adoptium (64-bit)
02:01:23.063 INFO  Load global settings
02:01:23.828 INFO  Load global settings (done) | time=765ms
02:01:23.855 INFO  Server id: 54000601-AZ-DAVF-MejkBZkEKtuI
02:01:23.949 INFO  Loading required plugins
02:01:23.951 INFO  Load plugins index
02:01:24.105 INFO  Load plugins index (done) | time=154ms
02:01:24.113 INFO  Load/download plugins
02:01:24.334 INFO  Load/download plugins (done) | time=222ms
02:01:27.340 INFO  Process project properties
02:01:27.493 INFO  Process project properties (done) | time=171ms
02:01:27.615 INFO  Project key: SBM-AI-ASSISTANT
02:01:27.618 INFO  Base dir: /usr/src/app
02:01:27.621 INFO  Working dir: /tmp/.scannerwork
02:01:27.705 INFO  Load project settings for component key: 'SBM-AI-ASSISTANT'
02:01:27.986 INFO  Load project settings for component key: 'SBM-AI-ASSISTANT' (done) | time=282ms
02:01:28.135 INFO  Load quality profiles
02:01:28.773 INFO  Load quality profiles (done) | time=639ms
02:01:29.120 INFO  Load active rules
02:01:33.138 INFO  Load active rules (done) | time=4004ms
02:01:33.239 INFO  Load analysis cache
02:01:33.541 INFO  Load analysis cache | time=304ms
02:01:35.203 INFO  Preprocessing files...
02:01:35.855 INFO  1 language detected in 48 preprocessed files (done) | time=661ms
02:01:35.857 INFO  11 files ignored because of inclusion/exclusion patterns
02:01:35.866 INFO  9 directories skipped because of exclusion patterns (content not counted)
02:01:35.867 INFO  7 files ignored because of scm ignore settings
02:01:35.886 INFO  Loading plugins for detected languages
02:01:35.892 INFO  Load/download plugins
02:01:36.133 INFO  Load/download plugins (done) | time=237ms
02:01:38.473 INFO  Load project repositories
02:01:39.246 INFO  Load project repositories (done) | time=778ms
02:01:39.572 INFO  Indexing files...
02:01:39.585 INFO  Project configuration:
02:01:39.608 INFO    Excluded sources: **/.venv/**, **/__pycache__/**, **/tests/**, backend/tests/**/*.py
02:01:39.613 INFO    Included tests: backend/tests/**/*.py
02:01:39.735 INFO  48 files indexed (done) | time=147ms
02:01:39.742 INFO  Quality profile for py: Sonar way
02:01:39.750 INFO  ------------- Run sensors on module SBM-AI-ASSISTANT
02:01:40.135 INFO  Load metrics repository
02:01:40.503 INFO  Load metrics repository (done) | time=364ms
02:01:43.388 INFO  Sensor IaC hadolint report Sensor [iac]
02:01:43.391 INFO  Sensor IaC hadolint report Sensor [iac] (done) | time=3ms
02:01:43.393 INFO  Sensor Java Config Sensor [iac]
02:01:44.924 INFO  There are no files to be analyzed for the Java language
02:01:44.933 INFO  Sensor Java Config Sensor [iac] (done) | time=1517ms
02:01:44.935 INFO  Sensor IaC Docker Sensor [iac]
02:01:44.986 INFO  There are no files to be analyzed for the Docker language
02:01:44.992 INFO  Sensor IaC Docker Sensor [iac] (done) | time=83ms
02:01:44.998 INFO  Sensor Python Sensor [python]
02:01:50.489 INFO  Starting global symbols computation
02:01:50.640 INFO  48 source files to be analyzed
02:02:00.843 INFO  11/48 files analyzed, current files: test_context_upgrade.py, contexts.py, test_documentation_export.py, ...
02:02:07.805 INFO  48/48 source files have been analyzed
02:02:07.808 INFO  Finished step global symbols computation in 17307ms
02:02:08.981 INFO  Starting rules execution
02:02:09.012 INFO  48 source files to be analyzed
02:02:19.185 INFO  5/48 files analyzed, current files: documentation_upgrade_service.py, file_discovery_service.py, documentation_export_service.py, ...
02:02:29.256 INFO  20/48 files analyzed, current files: contract_registry.py, ai.py, context_export_service.py, ...
02:02:39.661 INFO  39/48 files analyzed, current files: context_upgrade_service.py, documentation_retrieval_service.py, zip_export_service.py, ...
02:02:49.694 INFO  47/48 files analyzed, current file: context_upgrade_service.py
02:02:52.791 INFO  48/48 source files have been analyzed
02:02:52.798 INFO  Finished step rules execution in 43784ms
02:02:52.801 INFO  The Python analyzer was able to leverage cached data from previous analyses for 0 out of 48 files. These files were not parsed.
02:02:52.813 INFO  Sensor Python Sensor [python] (done) | time=67826ms
02:02:52.819 INFO  Sensor Cobertura Sensor for Python coverage [python]
02:02:54.024 INFO  Python test coverage
02:02:54.048 INFO  Parsing report '/usr/src/app/coverage.xml'
02:02:54.556 INFO  Sensor Cobertura Sensor for Python coverage [python] (done) | time=1737ms
02:02:54.559 INFO  Sensor PythonXUnitSensor [python]
02:02:55.476 INFO  Sensor PythonXUnitSensor [python] (done) | time=917ms
02:02:55.480 INFO  Sensor Python Dependency Sensor [python]
02:02:55.723 INFO  Sensor Python Dependency Sensor [python] (done) | time=216ms
02:02:55.728 INFO  Sensor TextAndSecretsSensor [text]
02:02:56.088 INFO  Available processors: 6
02:02:56.091 INFO  Using 6 threads for analysis.
02:02:58.469 INFO  Start fetching files for the text and secrets analysis
02:02:58.668 INFO  Using Git CLI to retrieve dirty files
02:02:58.762 WARN  Retrieving only language associated files, make sure to run the analysis inside a git repository to make use of inclusions specified via "sonar.text.inclusions"
02:02:58.771 INFO  Starting the text and secrets analysis
02:02:58.788 INFO  48 source files to be analyzed for the text and secrets analysis
02:02:59.703 INFO  48/48 source files have been analyzed for the text and secrets analysis
02:02:59.722 INFO  Sensor TextAndSecretsSensor [text] (done) | time=4019ms
02:02:59.767 INFO  ------------- Run sensors on project
02:03:00.492 INFO  Sensor IaC Project Sensor [iac]
02:03:00.503 INFO  Sensor IaC Project Sensor [iac] (done) | time=15ms
02:03:00.505 INFO  Sensor Zero Coverage Sensor
02:03:00.569 INFO  Sensor Zero Coverage Sensor (done) | time=66ms
02:03:00.572 INFO  ------------- Gather SCA dependencies on project
02:03:00.734 INFO  Dependency analysis skipped
02:03:00.913 INFO  CPD Executor 4 files had no CPD blocks
02:03:00.915 INFO  CPD Executor Calculating CPD for 39 files
02:03:01.150 INFO  CPD Executor CPD calculation finished (done) | time=233ms
02:03:01.254 INFO  SCM revision ID '56b7fc186362a7b88f87558e902eb74c2267a60f'
02:03:02.121 INFO  Analysis report generated in 877ms, dir size=1.7 MB
02:03:02.536 INFO  Analysis report compressed in 418ms, zip size=684.9 kB
02:03:03.083 INFO  Analysis report uploaded in 548ms
02:03:03.105 INFO  ANALYSIS SUCCESSFUL, you can find the results at: http://host.docker.internal:9000/dashboard?id=SBM-AI-ASSISTANT
02:03:03.106 INFO  Note that you will be able to access the updated dashboard once the server has processed the submitted analysis report
02:03:03.108 INFO  More about the report processing at http://host.docker.internal:9000/api/ce/task?id=dc515350-7de7-4609-95cd-2cacfc580469
02:03:03.212 INFO  Analysis total time: 1:38.502 s
02:03:03.227 INFO  SonarScanner Engine completed successfully
02:03:03.348 INFO  EXECUTION SUCCESS
02:03:03.381 INFO  Total time: 2:04.553s
Esperando procesamiento de SonarQube...
Quality Gate: OK
SonarQube Quality Gate aprobado.
```

## Evidence boundary

This file records only the output produced by the executed QA scripts.
It does not infer coverage, SonarQube status, deployments or quality gates not present in the logs.
