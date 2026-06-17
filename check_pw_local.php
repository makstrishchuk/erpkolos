<?php
$mysqli = new mysqli('db5018324043.hosting-data.io', 'dbu5430515', 'LinkinPark2131!', 'dbs14516218');
$email = 'm.trischuk@zolotojkolos.de';
$res = $mysqli->query("SELECT customers_password FROM customers WHERE customers_email_address='" . $mysqli->real_escape_string($email) . "' LIMIT 1");
$row = $res ? $res->fetch_assoc() : null;
$hash = $row ? $row['customers_password'] : '';
$tests = array('TempZK2026!', '11223344', 'Temp12345', 'Temp123456', 'TempPass2026!');
echo "hash=$hash\n";
foreach($tests as $p){
  echo $p . ' => ' . (password_verify($p, $hash) ? 'OK' : 'NO') . "\n";
}
?>