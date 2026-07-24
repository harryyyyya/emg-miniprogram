# Network isolation test failure and correction record

## Original board failure retained

The r2 Duo S board regression was **32/33**, not PASS:

- failed test: `test_slow_http_worker_does_not_block_signal_thread`
- original assertion: `self.assertLess(elapsed, 0.18)`
- measured elapsed time: `0.20893888000000516 s`
- result: `AssertionError: 0.20893888000000516 not less than 0.18`
- suite result: `Ran 33 tests in 30.232s`, `FAILED (failures=1)`

The unmodified returned log is preserved at:

`evidence/stagei_board_return/raw/stagei_evidence/10_board_offline_tests/unittest.log`

This failure is not deleted, relabelled, or presented as a PASS.

## Diagnostic basis

The failed test asserted that 20 parser/inference iterations must finish in
less than 0.18 seconds. The diagnostic demonstrated that this was an absolute
host-performance threshold below the Duo S baseline, rather than a valid test
of whether a slow HTTP worker blocked the signal path.

Returned five-run Duo S diagnostic:

- no-network baseline mean: 0.2101994719999311 s
- 200 ms mock-HTTP mean: 0.2146072799999274 s
- mean difference: 0.004407807999996294 s
- slow/baseline ratio: 1.0209696435393412
- both groups: 20 valid frames and 4 inferences per run
- slow group: 2 mock HTTP requests per run

The diagnostic source log is preserved at:

`evidence/stagei_board_return/raw/stagei_evidence/11_network_diagnostic/network_diagnostic.log`

## Correction scope and rerun

The product/runtime code is unchanged. The corrected unit test compares three
baseline runs with three slow-HTTP runs and fails if the median increment is
50 ms or more. A serialized 200 ms HTTP stall would fail this criterion with
substantial margin. This correction does not change the 40 ms pipeline
deadline or any BLE/controller contract.

After this test-only correction, the r3 Duo S regression recorded:

- `Ran 33 tests in 32.088s`
- `OK`
- 33/33 passed

The unmodified r3 log is preserved at:

`evidence/stagei_board_return/raw/stagei_evidence/12_board_tests_r3/unittest.log`
