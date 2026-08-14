package com.aigc.dashboard;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;

import org.json.JSONArray;
import org.json.JSONObject;

public class LocalServer {
    public static final int PORT = 9876;
    public static final String PH_HOST = "https://us.posthog.com";
    public static final int PH_PROJECT = 549467;

    private final String htmlTemplate;
    private final String phKey;

    public LocalServer(String htmlTemplate, String phKey) {
        this.htmlTemplate = htmlTemplate;
        this.phKey = phKey == null ? "" : phKey.trim();
    }

    public void start() {
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    ServerSocket ss = new ServerSocket(PORT, 16, InetAddress.getByName("127.0.0.1"));
                    while (true) {
                        Socket s = ss.accept();
                        handle(s);
                    }
                } catch (Exception ignore) {
                }
            }
        }, "dashboard-server").start();
    }

    private void handle(final Socket s) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    s.setSoTimeout(25000);
                    BufferedReader in = new BufferedReader(
                            new InputStreamReader(s.getInputStream(), StandardCharsets.UTF_8));
                    String line = in.readLine();
                    if (line == null) {
                        s.close();
                        return;
                    }
                    String[] parts = line.split(" ");
                    String target = parts.length > 1 ? parts[1] : "/";
                    while (line != null && !line.isEmpty()) {
                        line = in.readLine();
                    }
                    OutputStream out = s.getOutputStream();
                    if (target.startsWith("/api/overview")) {
                        byte[] body = overview().toString().getBytes(StandardCharsets.UTF_8);
                        respond(out, "200 OK", "application/json", body);
                    } else {
                        byte[] body = htmlTemplate
                                .replace("__REFRESH_MS__", "1000")
                                .getBytes(StandardCharsets.UTF_8);
                        respond(out, "200 OK", "text/html", body);
                    }
                    s.close();
                } catch (Exception ignore) {
                    try {
                        s.close();
                    } catch (Exception ignore2) {
                    }
                }
            }
        }, "http-handler").start();
    }

    private void respond(OutputStream out, String status, String ctype, byte[] body) throws Exception {
        String head = "HTTP/1.1 " + status + "\r\n"
                + "Content-Type: " + ctype + "; charset=utf-8\r\n"
                + "Content-Length: " + body.length + "\r\n"
                + "Connection: close\r\n\r\n";
        out.write(head.getBytes(StandardCharsets.UTF_8));
        out.write(body);
        out.flush();
    }

    private JSONObject overview() {
        JSONObject out = new JSONObject();
        try {
            out.put("ok", true);
            out.put("configured", true);
            out.put("updated", new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(new Date()));
            out.put("total_starts", num("SELECT count() FROM events WHERE event='app_start'"));
            out.put("today_starts", num("SELECT count() FROM events WHERE event='app_start' AND timestamp >= today()"));
            out.put("week_active", num("SELECT uniqExact(distinct_id) FROM events WHERE event IN ('app_start','heartbeat','detection_done') AND timestamp >= now() - INTERVAL 7 DAY"));
            out.put("month_active", num("SELECT uniqExact(distinct_id) FROM events WHERE event IN ('app_start','heartbeat','detection_done') AND timestamp >= now() - INTERVAL 30 DAY"));
            out.put("total_detections", num("SELECT count() FROM events WHERE event='detection_done'"));
            out.put("avg_session", num("SELECT avg(toFloat64OrNull(properties.duration_sec)) FROM events WHERE event='app_close' AND toFloat64OrNull(properties.duration_sec) > 0"));
            out.put("online_now", num("SELECT uniqExact(distinct_id) FROM events WHERE event='heartbeat' AND timestamp >= now() - INTERVAL 5 MINUTE"));

            JSONArray rows = query("SELECT toDate(timestamp) AS d, count() AS c FROM events "
                    + "WHERE event='app_start' AND timestamp >= now() - INTERVAL 30 DAY GROUP BY d ORDER BY d");
            JSONArray trend = new JSONArray();
            for (int i = 0; i < rows.length(); i++) {
                JSONArray r = rows.getJSONArray(i);
                JSONObject item = new JSONObject();
                item.put("date", String.valueOf(r.get(0)));
                item.put("count", r.get(1));
                trend.put(item);
            }
            out.put("trend", trend);
            out.put("engines", pairs("SELECT properties.engine, count() FROM events "
                    + "WHERE event='detection_done' AND properties.engine != '' "
                    + "GROUP BY properties.engine ORDER BY count() DESC LIMIT 8"));
            out.put("gpus", pairs("SELECT properties.gpu, count() FROM events "
                    + "WHERE event='app_start' AND properties.gpu != '' "
                    + "GROUP BY properties.gpu ORDER BY count() DESC LIMIT 8"));
            out.put("versions", pairs("SELECT properties.app_version, count() FROM events "
                    + "WHERE properties.app_version != '' "
                    + "GROUP BY properties.app_version ORDER BY count() DESC LIMIT 8"));
            out.put("downloads", JSONObject.NULL);
        } catch (Exception e) {
            try {
                out.put("ok", false);
                out.put("error", String.valueOf(e.getMessage()));
            } catch (Exception ignore) {
            }
        }
        return out;
    }

    private double num(String hogql) throws Exception {
        JSONArray rows = query(hogql);
        if (rows.length() == 0 || rows.getJSONArray(0).length() == 0) {
            return 0;
        }
        Object v = rows.getJSONArray(0).get(0);
        if (v == null || v == JSONObject.NULL) {
            return 0;
        }
        try {
            return Math.round(Double.parseDouble(String.valueOf(v)) * 10.0) / 10.0;
        } catch (Exception e) {
            return 0;
        }
    }

    private JSONArray pairs(String hogql) throws Exception {
        JSONArray rows = query(hogql);
        JSONArray out = new JSONArray();
        for (int i = 0; i < rows.length(); i++) {
            JSONArray r = rows.getJSONArray(i);
            JSONArray pair = new JSONArray();
            Object label = r.get(0);
            pair.put(label == null ? "未知" : String.valueOf(label));
            pair.put(r.get(1));
            out.put(pair);
        }
        return out;
    }

    private JSONArray query(String hogql) throws Exception {
        JSONObject inner = new JSONObject();
        inner.put("kind", "HogQLQuery");
        inner.put("query", hogql);
        JSONObject payload = new JSONObject();
        payload.put("query", inner);

        URL url = new URL(PH_HOST + "/api/projects/" + PH_PROJECT + "/query/");
        HttpURLConnection c = (HttpURLConnection) url.openConnection();
        c.setRequestMethod("POST");
        c.setRequestProperty("Authorization", "Bearer " + phKey);
        c.setRequestProperty("Content-Type", "application/json");
        c.setConnectTimeout(20000);
        c.setReadTimeout(30000);
        c.setDoOutput(true);
        c.getOutputStream().write(payload.toString().getBytes(StandardCharsets.UTF_8));
        int code = c.getResponseCode();
        InputStream is = code >= 400 ? c.getErrorStream() : c.getInputStream();
        String resp = new String(readAll(is), StandardCharsets.UTF_8);
        c.disconnect();
        JSONObject j = new JSONObject(resp);
        if (!j.has("results")) {
            throw new Exception("PostHog " + code + ": " + resp.substring(0, Math.min(200, resp.length())));
        }
        return j.getJSONArray("results");
    }

    private byte[] readAll(InputStream is) throws Exception {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = is.read(buf)) > 0) {
            bos.write(buf, 0, n);
        }
        is.close();
        return bos.toByteArray();
    }
}
