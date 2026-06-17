<?php
require '/homepages/4/d374706423/htdocs/shop/site/Dateien/neue/Dateien/includes/configure.php';
$mysqli = new mysqli(DB_SERVER, DB_SERVER_USERNAME, DB_SERVER_PASSWORD, DB_DATABASE);
if($mysqli->connect_error){fwrite(STDERR, $mysqli->connect_error."\n"); exit(1);} 
$mysqli->set_charset('utf8mb4');
$tables=[];
$res=$mysqli->query("SHOW TABLES LIKE 'content%'");
while($row=$res->fetch_row()){ $tables[]=$row[0]; }
echo "TABLES\n";
foreach($tables as $t){ echo $t."\n"; }

$q="SELECT content_group, language_id, content_title, content_url FROM content_manager WHERE content_status=1 ORDER BY content_group, language_id";
if($r=$mysqli->query($q)){
  echo "\nCONTENT_MANAGER\n";
  while($row=$r->fetch_assoc()){
    echo $row['content_group']."\t".$row['language_id']."\t".$row['content_title']."\t".$row['content_url']."\n";
  }
}else{
  echo "Query failed: ".$mysqli->error."\n";
}
$mysqli->close();
?>
