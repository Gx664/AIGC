package com.aigc.dashboard;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

public class MainActivity extends Activity {
    private WebView web;
    private FrameLayout overlay;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        try {
            FrameLayout root = new FrameLayout(this);
            web = new WebView(this);
            web.getSettings().setJavaScriptEnabled(true);
            web.getSettings().setDomStorageEnabled(true);
            web.setWebViewClient(new WebViewClient() {
                @Override
                public void onPageFinished(WebView view, String url) {
                    if (overlay != null) {
                        overlay.postDelayed(new Runnable() {
                            @Override
                            public void run() {
                                overlay.setVisibility(android.view.View.GONE);
                            }
                        }, 1000);
                    }
                }
            });
            root.addView(web, new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));

            overlay = new FrameLayout(this);
            overlay.setBackgroundColor(Color.rgb(11, 18, 32));
            LinearLayout box = new LinearLayout(this);
            box.setOrientation(LinearLayout.VERTICAL);
            box.setGravity(Gravity.CENTER);
            ProgressBar pb = new ProgressBar(this);
            TextView status = new TextView(this);
            status.setText("正在检查配置并连接数据...\n（首次加载约 3~10 秒）");
            status.setTextColor(Color.rgb(148, 163, 184));
            box.addView(pb);
            box.addView(status);
            FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT);
            lp.gravity = Gravity.CENTER;
            overlay.addView(box, lp);
            root.addView(overlay, new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));

            setContentView(root);
            new LocalServer(readAsset("dashboard.html"), readAsset("posthog_key.txt")).start();
            web.loadUrl("http://127.0.0.1:9876/");
        } catch (Exception e) {
            try {
                setContentView(new TextView(this) {{
                    setText("启动失败：" + e);
                    setTextColor(Color.WHITE);
                }});
            } catch (Exception ignore) {
            }
        }
    }

    private String readAsset(String name) {
        try {
            java.io.InputStream is = getAssets().open(name);
            java.io.ByteArrayOutputStream bos = new java.io.ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = is.read(buf)) > 0) {
                bos.write(buf, 0, n);
            }
            is.close();
            return bos.toString("UTF-8");
        } catch (Exception e) {
            return "<html><body>assets error: " + e + "</body></html>";
        }
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
