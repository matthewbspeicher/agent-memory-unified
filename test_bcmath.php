<?php
$parent_entry = "10.12345678";
$child_entry = "12.98765432";
$parent_qty = "3.33333333";
$child_qty = "1.11111111";
$parent_fees = "0.11111111";
$child_fees = "0.05555555";

$grossPnl = bcmul(bcsub($child_entry, $parent_entry, 8), $child_qty, 8);
$feeShare = bcmul($parent_fees, bcdiv($child_qty, $parent_qty, 8), 8);
$totalFees = bcadd($feeShare, $child_fees, 8);
$netPnl = bcsub($grossPnl, $totalFees, 8);
$costBasis = bcmul($parent_entry, $child_qty, 8);
$pnlPercent = bcmul(bcdiv($netPnl, $costBasis, 8), '100', 4);

echo json_encode([
    'net_pnl' => $netPnl,
    'pnl_percent' => $pnlPercent
]) . "\n";
