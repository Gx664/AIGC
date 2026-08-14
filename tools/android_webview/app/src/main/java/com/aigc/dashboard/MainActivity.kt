package com.aigc.dashboard

import android.annotation.SuppressLint
import android.graphics.Color
import android.os.Bundle
import android.view.View
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    // ===== 打包前改这里：填你电脑的局域网地址，例如 "http://192.168.1.100:8765" =====
    // 填了之后，APK 装到手机，打开就直接显示数据，无需任何设置。
    // 留空则首次打开会出现一个地址输入框（输入一次，以后自动记住）。
    private val DEFAULT_URL = ""

    private lateinit var web: WebView
    private lateinit var urlBar: LinearLayout
    private lateinit var urlInput: EditText

    private val prefs by lazy { getSharedPreferences("dashboard", MODE_PRIVATE) }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = LinearLayout(this)
        root.orientation = LinearLayout.VERTICAL

        urlBar = LinearLayout(this)
        urlBar.orientation = LinearLayout.HORIZONTAL
        urlBar.setPadding(10, 10, 10, 10)
        urlBar.setBackgroundColor(Color.rgb(15, 23, 42))
        urlInput = EditText(this)
        urlInput.hint = "输入电脑看板地址，如 192.168.1.100:8765"
        urlInput.setTextColor(Color.WHITE)
        urlInput.setHintTextColor(Color.rgb(148, 163, 184))
        val btn = Button(this)
        btn.text = "连接"
        urlBar.addView(
            urlInput,
            LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        )
        urlBar.addView(btn)
        root.addView(urlBar)

        web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.webViewClient = WebViewClient()
        root.addView(
            web,
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f)
        )
        setContentView(root)

        val saved = prefs.getString("url", "")
        when {
            !saved.isNullOrEmpty() -> openUrl(saved)
            DEFAULT_URL.isNotEmpty() -> openUrl(DEFAULT_URL)
            else -> btn.setOnClickListener { connect() }
        }
    }

    private fun connect() {
        var u = urlInput.text.toString().trim()
        if (u.isEmpty()) {
            Toast.makeText(this, "请输入地址", Toast.LENGTH_SHORT).show()
            return
        }
        if (!u.startsWith("http")) {
            u = "http://$u"
        }
        prefs.edit().putString("url", u).apply()
        openUrl(u)
    }

    private fun openUrl(u: String) {
        urlBar.visibility = View.GONE
        web.loadUrl(u)
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }
}
