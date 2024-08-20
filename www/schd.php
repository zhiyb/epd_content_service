<?php
// Data delivery scheduling system

function error($code, $msg = null) {
    http_response_code($code);
    if ($msg)
        die(json_encode(["code" => $code, "msg" => $msg]));
    die(json_encode(["code" => $code]));
}

// Connect to database
class Database
{
    public $db;
    public $service;

    public function __construct($service)
    {
        $this->service = $service;
        require 'dbconf.php';
        $this->db = new mysqli($dbhost, $dbuser, $dbpw, $dbname);
        if ($this->db->connect_error)
            error(500, "Connection failed: " . $this->db->connect_error . "\n");
        $this->db->set_charset('utf8mb4');
    }

    public function get($client, $key) {
        $stmt = $this->db->prepare(
            "SELECT `value` FROM `services` WHERE `service` = ? AND `client` = ? AND `key` = ?");
        $stmt->bind_param('sss', $this->service, $client, $key);
        if ($stmt->execute() !== true)
            error(500, $stmt->error);
        $res = $stmt->get_result();
        if (!$res)
            return null;
        $res = $res->fetch_row();
        if (!$res)
            return null;
        return $res[0];
    }

    public function getClientValues($key) {
        $stmt = $this->db->prepare(
            "SELECT UNIQUE `client`, `value` FROM `services` WHERE `service` = ? AND `key` = ?");
        $stmt->bind_param('ss', $this->service, $key);
        if ($stmt->execute() !== true)
            error(500, $stmt->error);
        $res = $stmt->get_result();
        if (!$res)
            return null;
        $res = $res->fetch_all(MYSQLI_ASSOC);
        if (!$res)
            return null;
        $ret = [];
        foreach ($res as $row)
            $ret[$row['client']] = $row['value'];
        return $ret;
    }

    public function getKeyValues($client) {
        $stmt = $this->db->prepare(
            "SELECT UNIQUE `key`, `value` FROM `services` WHERE `service` = ? AND `client` = ?");
        $stmt->bind_param('ss', $this->service, $client);
        if ($stmt->execute() !== true)
            error(500, $stmt->error);
        $res = $stmt->get_result();
        if (!$res)
            return null;
        $res = $res->fetch_all(MYSQLI_ASSOC);
        if (!$res)
            return null;
        $ret = [];
        foreach ($res as $row)
            $ret[$row['key']] = $row['value'];
        return $ret;
    }

    public function set($client, $key, $val) {
        $sql = <<<SQL
            INSERT INTO `services` (`service`, `client`, `key`, `value`)
            VALUES (?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE `value` = VALUES(`value`)
        SQL;
        $stmt = $this->db->prepare($sql);
        $stmt->bind_param('sssb', $this->service, $client, $key, $null);
        $stmt->send_long_data(3, $val);
        if ($stmt->execute() !== true)
            error(500, $stmt->error);
    }
}

$db = new Database("schd");

$admin = $db->get("admin", "token");
$action = $_GET['action'] ?? null;
$token = $_GET['token'] ?? $_POST['token'] ?? null;
if ($admin !== null)
    $admin = $admin === $token;

if ($admin === false && $token && !(int)$db->get($token, "enrolled"))
    error(401, "Invalid token");

$reserved_keys = ["enrolled", "update_seq", "update_ts", "read_seq", "read_ts"];


// ================================
if ($action == "setup") {
    if ($admin !== null)
        error(401);
    if (!$token)
        error(400);

    $db->set("admin", "token", $token);

    // Back to log in
    $admin = false;
    $token = null;


// ================================
} else if ($action == "enroll") {
    if (!$admin)
        error(401);
    $dev_token = $_POST['dev_token'] ?? null;
    if (!$dev_token)
        error(400);

    $db->set($dev_token, "enrolled", "1");


// ================================
} else if ($action == "remove") {
    if (!$admin)
        error(401);
    $dev_token = $_POST['dev_token'] ?? null;
    if (!$dev_token)
        error(400);

    $db->set($dev_token, "enrolled", "0");


// ================================
} else if ($action == "schedule") {
    if ($admin)
        error(400, "Invalid token");
    $ts = $_GET['ts'] ?? null;
    if (!$ts)
        error(400, "Invalid timestamp");
    $dt = DateTime::createFromFormat(DateTime::RFC3339, $ts);
    if (!$dt)
        error(400, "Invalid timestamp");

    $ts = $dt->format(DateTime::RFC3339);
    $db->set($token, "update_ts", $ts);
    $db->set($token, "update_seq", ((int)($db->get($token, "update_seq")) + 1) % 65536);
    error(200, "OK");


// ================================
} else if ($action == "next") {
    if ($admin)
        error(400, "Invalid token");

    $update_seq = (int)($db->get($token, 'update_seq') ?? 0);
    $read_seq = (int)($db->get($token, 'read_seq') ?? 0);

    $now = new DateTime("now", new DateTimeZone("UTC"));
    $update_ts = $db->get($token, 'update_ts');
    if (!$update_ts)
        error(400, "Invalid update timestamp");
    $update_dt = DateTime::createFromFormat(DateTime::RFC3339, $update_ts);
    if (!$update_dt)
        error(400, "Invalid update timestamp");

    $ret = [
        "outdated" => $update_seq != $read_seq,
        "next_schd_s" => $update_dt->getTimestamp() - $now->getTimestamp()
    ];
    echo(json_encode($ret));
    die();


// ================================
} else if ($action == "update") {
    if ($admin)
        error(400, "Invalid token");
    if ($_SERVER["REQUEST_METHOD"] != "POST")
        error(400, "Invalid method");
    if (!$_GET['token']) {
        // Form submission
        $key = $_POST['key'] ?? 'data';
        $data = $_POST['data'];
    } else {
        $key = $_GET['key'] ?? 'data';
        $data = file_get_contents("php://input");
    }
    if (empty($key) || in_array($key, $reserved_keys))
        error(400, "Invalid key");

    $db->set($token, $key, $data);
    error(200, "OK");


// ================================
} else if ($action == "peek") {
    if ($admin)
        error(400, "Invalid token");
    $key = $_GET['key'] ?? 'data';
    if (empty($key) || in_array($key, $reserved_keys))
        error(400, "Invalid key");
    $mime = $_GET['mime'] ?? 'application/octet-stream';

    header("Content-Type: $mime");
    header("Content-Disposition: inline; filename=\"$key.bin\"");
    echo($db->get($token, $key));
    die();


// ================================
} else if ($action == "read") {
    if ($admin)
        error(400, "Invalid token");
    $key = $_GET['key'] ?? 'data';
    if (empty($key) || in_array($key, $reserved_keys))
        error(400, "Invalid key");

    $now = new DateTime("now", new DateTimeZone("UTC"));
    $ts = $now->format(DateTime::RFC3339);

    header('Content-Type: application/octet-stream');
    header("Content-Disposition: inline; filename=\"$key.bin\"");
    echo($db->get($token, $key));

    $db->set($token, "read_ts", $ts);
    $db->set($token, "read_seq", (int)$db->get($token, "update_seq"));
    die();
}


// ================================
// UI
?>
<html>
<head>
<title>Data delivery scheduling system</title>
<meta charset="utf-8">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
table {
    border-collapse: collapse;
    border-style: hidden;
}

table td, table th {
    border: 1px solid black;
    padding: 4px;
    text-align: left;
}
</style>
</head>
<body>
<h1>Data delivery scheduling system</h1>
<?php

// ================================

if ($admin === null): ?>
<h2>Initial setup</h2>
<form action="?action=setup" method="post">
    <label for="token">Admin token:</label><br>
    <input type="password" id="token" name="token">
    <input type="submit" value="Submit">
</form>
<?php

// ================================

elseif ($token === null): ?>
<h2>Login</h2>
<form action="?action=login" method="post">
    <label for="token">Token:</label><br>
    <input type="password" id="token" name="token">
    <input type="submit" value="Submit">
</form>
<?php

// ================================

elseif ($admin): ?>
<h2>Admin portal</h2>
<hr>
<h3>Devices</h3>
<?php
$devices = $db->getClientValues("enrolled");
foreach ($devices as $dev_token => $enrolled)
    if ($enrolled)
        echo("<a href=\"?token=${dev_token}\">${dev_token}</a><br>");
?>
<br>
<form action="?action=enroll" method="post">
    <input type="hidden" id="token" name="token" value="<?php echo($token) ?>">
    <label for="dev_token">Enroll device token:</label><br>
    <input type="text" id="dev_token" name="dev_token">
    <input type="submit" value="Submit">
</form>
<form action="?action=remove" method="post">
    <input type="hidden" id="token" name="token" value="<?php echo($token) ?>">
    <label for="dev_token">Remove device token:</label><br>
    <input type="text" id="dev_token" name="dev_token">
    <input type="submit" value="Submit">
</form>
<?php

// ================================

else: ?>
<h2>Device management</h2>
<table>
    <tr>
        <th>Token</th>
        <td><?php echo($token) ?></td>
    </tr>
</table>
<hr>
<?php
$c = $db->getKeyValues($token);
//var_dump($c);

$now = new DateTime("now", new DateTimeZone("UTC"));
$ts = $now->format(DateTime::RFC3339);

$update_seq = (int)($c['update_seq'] ?? 0);
$update_ts = $c['update_ts'] ?? null;
$update_dt = null;
if ($update_ts)
    $update_dt = DateTime::createFromFormat(DateTime::RFC3339, $update_ts);
$update_missed = !$update_dt || $now >= $update_dt;

$read_seq = (int)($c['read_seq'] ?? 0);
$read_ts = $c['read_ts'] ?? null;
$read_missed = $read_seq != $update_seq;
?>
<h3>Schedule</h3>
<table>
    <tr>
        <th></th>
        <th>Time</th>
        <th>Seq ID</th>
        <th>Missed</th>
    </tr>
    <tr>
        <th>Update</th>
        <td><?php echo($update_ts ?? "null"); ?></td>
        <td><?php echo($update_seq); ?></td>
        <td><?php echo($update_missed ? "⚠" : ""); ?></td>
    </tr>
    <tr>
        <th>Read</th>
        <td><?php echo($read_ts ?? "null"); ?></td>
        <td><?php echo($read_seq); ?></td>
        <td><?php echo($read_missed ? "⚠" : ""); ?></td>
    </tr>
</table>
<hr>
<h3>Operations</h3>
<table>
<?php
$url_token = urlencode($token);
$url_ts = urlencode($ts);

$links = [
    ["Next schedule info", "?token=$url_token&action=next"],
    ["Update schedule", "?token=$url_token&action=schedule&ts=$url_ts"],
    ["Update data", "?token=$url_token&action=update"],
    ["Update metadata", "?token=$url_token&action=update&key=meta"],
    ["Read data", "?token=$url_token&action=read"],
    ["Peek data", "?token=$url_token&action=peek"],
    ["Peek metadata", "?token=$url_token&action=peek&key=meta&mime=" . urlencode("text/plain")],
];

foreach ($links as $link) {
    $type = $link[0];
    $url = $link[1];
    echo("<tr><th>${type}</th><td><a href=\"${url}\">${url}</a></td></tr>");
}
?>
</table>
<hr>
<h3>Data</h3>
<table>
<?php
foreach ($c as $key => $val) {
    if (!in_array($key, $reserved_keys)) {
        $len = strlen($val);
        $peek = "?token=$url_token&action=peek";
        if ($key != "data")
            $peek .= "&key=" . urlencode($key);
        $preview = 64;
        $str = substr($val, 0, $preview);
        $str = htmlspecialchars($str);
        $str = json_encode($str);
        if (strlen($str) > $preview)
            $str = substr($str, 0, $preview) . "...";
        //$str = str_replace(['<', '>'], ['&lt;', '&gt;'], $str);
        $str = "<code>$str</code>";
        echo("<tr><th>$key</th><td>$len byte(s)</td><td><a href=\"$peek\">Download</a></td><td>$str</td></tr>");
    }
}
?>
</table>
<br>
<form action="?action=update" method="post">
    <input type="hidden" id="token" name="token" value="<?php echo($token) ?>">
    <label>Update metadata:</label><br>
    <input type="text" id="key" name="key">
    <label>=</label>
    <input type="text" id="data" name="data">
    <input type="submit" value="Submit">
</form>
<?php endif; ?>
</body>
