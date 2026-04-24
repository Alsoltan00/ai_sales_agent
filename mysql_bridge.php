<?php
/**
 * Universal MySQL Bridge for AI Sales Agent
 * ----------------------------------------
 * Upload this file to your InfinityFree (or any) hosting to bypass Firewall/Remote MySQL restrictions.
 * Usage: https://your-site.com/mysql_bridge.php
 */

header('Content-Type: application/json');

// --- CONFIGURATION ---
$db_host = "sql100.infinityfree.com"; 
$db_user = "if0_41719311";
$db_pass = "YOUR_MYSQL_PASSWORD"; // <--- CHANGE THIS
$db_name = "if0_41719311_pickline";
$table_name = "products";

// --- CONNECTION ---
$conn = new mysqli($db_host, $db_user, $db_pass, $db_name);

if ($conn->connect_error) {
    die(json_encode(["error" => "Connection failed: " . $conn->connect_error]));
}

// Ensure UTF-8
$conn->set_charset("utf8mb4");

// --- QUERY ---
$result = $conn->query("SELECT * FROM $table_name LIMIT 1000");

$data = [];
if ($result) {
    while($row = $result->fetch_assoc()) {
        $data[] = $row;
    }
}

// --- OUTPUT ---
echo json_encode($data, JSON_UNESCAPED_UNICODE);

$conn->close();
?>
