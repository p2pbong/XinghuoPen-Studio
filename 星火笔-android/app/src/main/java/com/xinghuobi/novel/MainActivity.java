package com.xinghuobi.novel;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.net.Uri;
import android.os.Bundle;
import android.speech.RecognizerIntent;
import android.webkit.JsResult;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.core.content.FileProvider;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;

/** 星火笔·安卓版：Python 引擎（复用桌面端 RP 管线）以本地 API 服务运行，
 *  WebView 加载打包的前端（assets/www），fetch 到 127.0.0.1:<port>/api/* 完成闭环。
 *  v0.13：项目对接桥——pickZip 系统文件选择（导入 zip）、shareFile 系统分享（导出 zip）。
 *  v0.16：语音码字桥——launchVoiceInput 系统语音识别（RecognizerIntent）→ __voiceReady 回调。 */
public class MainActivity extends Activity {
    private static final int REQ_PICK_ZIP = 1001;
    private static final int REQ_VOICE = 1002;
    private static final int REQ_PICK_TXT = 1003;
    private WebView web;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }
        File filesDir = getFilesDir();
        int port = Python.getInstance()
                .getModule("android_server")
                .callAttr("start_app", filesDir.getAbsolutePath(), this)
                .toInt();

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        // file:// 页面 fetch 本地 http 服务：放开 mixed content（仅本机 127.0.0.1）
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        // v1.42 修复安卓端功能全挂：
        // ① file:// 页面（origin=null）fetch http://127.0.0.1 触发 CORS 预检——
        //    setAllowUniversalAccessFromFileURLs 让 WebView 放行（配合服务端 CORS 头双保险）；
        // ② <img src="file:///android_asset/www/icons/*.svg"> 同类被 CORS 拦截导致导航图标
        //    空白——setAllowFileAccessFromFileURLs 允许 file 页面内加载 file 资源。
        s.setAllowUniversalAccessFromFileURLs(true);
        s.setAllowFileAccessFromFileURLs(true);
        web.setWebViewClient(new WebViewClient());
        // v1.13：必须设 WebChromeClient，否则 WebView 里 JS 的 alert()/confirm() 会被静默吞掉
        // （拉取模型失败提示、删除确认等全部"点了没反应"）
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onJsAlert(WebView view, String url, String message, JsResult result) {
                new AlertDialog.Builder(MainActivity.this)
                        .setMessage(message)
                        .setPositiveButton("确定", new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int w) {
                                result.confirm();
                            }
                        })
                        .setOnCancelListener(new DialogInterface.OnCancelListener() {
                            @Override
                            public void onCancel(DialogInterface d) {
                                result.cancel();
                            }
                        })
                        .show();
                return true;
            }

            @Override
            public boolean onJsConfirm(WebView view, String url, String message, JsResult result) {
                new AlertDialog.Builder(MainActivity.this)
                        .setMessage(message)
                        .setPositiveButton("确定", new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int w) {
                                result.confirm();
                            }
                        })
                        .setNegativeButton("取消", new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int w) {
                                result.cancel();
                            }
                        })
                        .setOnCancelListener(new DialogInterface.OnCancelListener() {
                            @Override
                            public void onCancel(DialogInterface d) {
                                result.cancel();
                            }
                        })
                        .show();
                return true;
            }
        });
        web.loadUrl("file:///android_asset/www/index.html?port=" + port);
        setContentView(web);
    }

    /** 供 Python 调用：切换屏幕方向（sensor=跟随系统 / portrait / landscape）。
     *  配合 manifest configChanges，旋转只触发 CSS 重排（WebView 不重建，输入内容保留）。
     *  Python 侧在 HTTP 后台线程调用，setRequestedOrientation 必须切回 UI 线程执行。 */
    public void setOrientation(String mode) {
        int o = ActivityInfo.SCREEN_ORIENTATION_SENSOR;
        if ("portrait".equals(mode)) o = ActivityInfo.SCREEN_ORIENTATION_PORTRAIT;
        else if ("landscape".equals(mode)) o = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE;
        final int target = o;
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                setRequestedOrientation(target);
            }
        });
    }

    /** 供 Python 调用：打开系统文件选择器选项目 zip（导入）。 */
    public void pickZip() {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        i.putExtra(Intent.EXTRA_MIME_TYPES,
                new String[]{"application/zip", "application/octet-stream"});
        try {
            startActivityForResult(i, REQ_PICK_ZIP);
        } catch (Exception e) {
            // 无文件管理器等：忽略
        }
    }

    /** 供 Python 调用：打开系统文件选择器选小说 txt（v0.55 拆书工坊）。 */
    public void pickTxt() {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        i.putExtra(Intent.EXTRA_MIME_TYPES,
                new String[]{"text/plain", "text/*", "application/octet-stream"});
        try {
            startActivityForResult(i, REQ_PICK_TXT);
        } catch (Exception e) {
            // 无文件管理器等：忽略
        }
    }

    /** 供 Python 调用：系统分享面板发送文件（zip/epub/txt 按扩展名识别 MIME）。 */
    public void shareFile(String path) {
        try {
            File f = new File(path);
            Uri uri = FileProvider.getUriForFile(this,
                    "com.xinghuobi.novel.fileprovider", f);
            Intent send = new Intent(Intent.ACTION_SEND);
            String name = f.getName().toLowerCase();
            if (name.endsWith(".epub")) send.setType("application/epub+zip");
            else if (name.endsWith(".zip")) send.setType("application/zip");
            else if (name.endsWith(".txt")) send.setType("text/plain");
            else send.setType("application/octet-stream");
            send.putExtra(Intent.EXTRA_STREAM, uri);
            send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(Intent.createChooser(send, "分享文件"));
        } catch (Exception e) {
            // 分享失败时前端仍显示本地路径
        }
    }

    /** 供 Python 调用：唤起系统语音识别（v0.16 语音码字）。
     *  用户说完后 onActivityResult 取识别文本，回调前端 window.__voiceReady(text)。 */
    public void launchVoiceInput() {
        try {
            Intent i = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
            i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                    RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
            i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "zh-CN");
            i.putExtra(RecognizerIntent.EXTRA_PROMPT, "说出要输入的内容…");
            startActivityForResult(i, REQ_VOICE);
        } catch (Exception e) {
            // 无语音识别服务：前端仍提示
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_VOICE && resultCode == RESULT_OK && data != null) {
            ArrayList<String> res = data.getStringArrayListExtra(
                    RecognizerIntent.EXTRA_RESULTS);
            if (res != null && !res.isEmpty() && web != null) {
                String text = res.get(0);
                String js = "window.__voiceReady && window.__voiceReady("
                        + JSONObject.quote(text == null ? "" : text) + ")";
                web.evaluateJavascript(js, null);
            }
            return;
        }
        if (resultCode != RESULT_OK) return;
        if (requestCode == REQ_PICK_TXT) {
            onPickTxt(data);
            return;
        }
        if (requestCode != REQ_PICK_ZIP) return;
        if (data == null || data.getData() == null) return;
        try {
            InputStream in = getContentResolver().openInputStream(data.getData());
            File dir = new File(getFilesDir(), "imports");
            dir.mkdirs();
            File out = new File(dir, "picked.zip");
            OutputStream os = new FileOutputStream(out);
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) os.write(buf, 0, n);
            os.close();
            in.close();
            if (web != null) {
                web.evaluateJavascript(
                        "window.__importReady && window.__importReady('picked.zip')", null);
            }
        } catch (Exception e) {
            // 读取失败：前端可提示
        }
        return;
    }

    /** 拆书 txt 选择结果处理（v0.55）：保存到 imports/picked.txt → 回调 window.__breakTxtReady。 */
    private void onPickTxt(Intent data) {
        if (data == null || data.getData() == null) return;
        try {
            InputStream in = getContentResolver().openInputStream(data.getData());
            File dir = new File(getFilesDir(), "imports");
            dir.mkdirs();
            File out = new File(dir, "picked.txt");
            OutputStream os = new FileOutputStream(out);
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) os.write(buf, 0, n);
            os.close();
            in.close();
            if (web != null) {
                web.evaluateJavascript(
                        "window.__breakTxtReady && window.__breakTxtReady('picked.txt')", null);
            }
        } catch (Exception e) {
            // 读取失败：前端可提示
        }
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
