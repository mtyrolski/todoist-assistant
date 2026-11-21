# These entry points are invoked by the bundled dashboard through WebView, not Java callers.
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
