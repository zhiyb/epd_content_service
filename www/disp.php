<?php
require 'dbconf.php';
//ob_start("ob_gzhandler", 4 * 1024 * 1024);

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

	$size = 0;
	if (array_key_exists('size', $_GET))
		$size = $_GET['size'];
	$offset = 0;
	if (array_key_exists('ofs', $_GET))
		$offset = $_GET['ofs'];

	$ret = substr($ret, $offset, $size);
}

if (array_key_exists('png', $_GET)) {
	$uuid = $_GET['png'];
	$sql = <<<SQL
	SELECT data FROM thumbnail
	INNER JOIN device ON device.uuid = ? AND device.type = "disp" AND thumbnail.id = device.id
	LIMIT 1
SQL;
        $stmt = $db->prepare($sql);
        $stmt->bind_param('s', $uuid);
	$stmt->execute();
	$obj = $stmt->get_result();
	if (!$obj)
		error(400, "No record");
	$ret = $obj->fetch_column();

	header('Content-Type: image/png');
	header('Content-disposition: filename="disp_' . $uuid . '_' . date("Ymd_His") . '.png"');
	//ob_start("ob_gzhandler", 4 * 1024 * 1024);
}

else if (array_key_exists('info', $_GET)) {
	$uuid = $_GET['info'];
	$sql = <<<SQL
	SELECT info FROM device WHERE type = "disp" AND uuid = ?
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

else if (array_key_exists('schd', $_GET)) {
	$uuid = $_GET['schd'];
	$sql = <<<SQL
	SELECT last, next FROM schedule
	INNER JOIN device ON device.uuid = ? AND device.type = "disp" AND schedule.id = device.id
	LIMIT 1
SQL;
        $stmt = $db->prepare($sql);
        $stmt->bind_param('s', $uuid);
	$stmt->execute();
	$obj = $stmt->get_result();
	if (!$obj)
		error(400, "No record");
	$ret = $obj->fetch_assoc();
	if ($ret === null)
		error(400, "No record");
	$ret = json_encode($ret);
}

else if (array_key_exists('upd', $_GET)) {
	if ($_SERVER["REQUEST_METHOD"] != "POST")
	    error(400, "Invalid method");

	$data = file_get_contents("php://input");

	$uuid = $_GET['upd'];
	$sql = <<<SQL
	INSERT INTO display (id, data)
	SELECT id, ?
	FROM device
	WHERE device.uuid = ?
	ON DUPLICATE KEY UPDATE data = VALUES(data)
SQL;
        $stmt = $db->prepare($sql);
        $stmt->bind_param('bs', $null, $uuid);
	$stmt->send_long_data(0, $data);
	if (!$stmt->execute())
		error(400, "No record");
	$ret = json_encode(array("error" => 0));
}

else if (array_key_exists('thumb', $_GET)) {
	if ($_SERVER["REQUEST_METHOD"] != "POST")
	    error(400, "Invalid method");

	$data = file_get_contents("php://input");

	$uuid = $_GET['thumb'];
	$sql = <<<SQL
	INSERT INTO thumbnail (id, data)
	SELECT id, ?
	FROM device
	WHERE device.uuid = ?
	ON DUPLICATE KEY UPDATE data = VALUES(data)
SQL;
        $stmt = $db->prepare($sql);
        $stmt->bind_param('bs', $null, $uuid);
	$stmt->send_long_data(0, $data);
	if (!$stmt->execute())
		error(400, "No record");
	$ret = json_encode(array("error" => 0));
}

if ($ret === null) {
	error(400, "Unknown operation");
}

header('Content-Type: text/plain');
echo($ret);
?>
