补传内容说明

本目录已包含能够放入最终 ZIP 的补传材料：

1. RESULT_RETURN.txt
2. board_replay_10rounds.json
3. Stage H 原始板端返回文件：board_replay_stdout.txt、environment.txt、
   exit_code.txt、native_feature_sha256.txt
4. Stage H 原始板端结果 ZIP 及其 sidecar
5. Stage G 原始 HCI 审计 ZIP、sidecar、commands_executed.txt、
   duos_stageg_hci_test.txt、duos_stageg_step1.txt

最终文件 duo_fc_f8_stageh_f2_bound_final.zip 不能包含它自己，否则会形成
无限递归。它自己的最终 SHA256 sidecar 也不能放入 ZIP 内，因为把 sidecar
加入 ZIP 后 ZIP 内容和哈希会再次改变，使该 sidecar 立即失效。

因此最终 ZIP 与有效 sidecar 位于 final_delivery 目录下，并与本 ZIP 同级
交付。此限制只涉及自引用结构，不影响本目录中其他补传证据的完整性。
