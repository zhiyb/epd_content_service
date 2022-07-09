<?php
require 'dbconf.php';
ob_start("ob_gzhandler", 4 * 1024 * 1024);

function error($code, $msg = null) {
    http_response_code($code);
    if ($msg)
        die('ERROR ' . $code . ': ' . $msg);
    die();
}

$db = new mysqli($dbhost, $dbuser, $dbpw, $dbname);
if ($db->connect_error)
    error(500, "Connection failed: " . $db->connect_error);
$db->set_charset('utf8mb4');

$uuid = null;
$ret = null;

if (array_key_exists('get', $_GET)) {
	$uuid = $_GET['get'];
	$sql = <<<SQL
	SELECT data FROM display
	INNER JOIN device ON device.uuid = ? AND device.type = "disp" AND display.id = device.id
	LIMIT 1
SQL;
        $stmt = $db->prepare($sql);
        $stmt->bind_param('s', $uuid);
	$stmt->execute();
	$obj = $stmt->get_result();
	if (!$obj)
		error(400, "No record");
	$ret = $obj->fetch_column();
}

if ($ret === null) {
	error(400, "Unknown operation");
}

header('Content-Type: text/plain');
echo($ret);
?>
