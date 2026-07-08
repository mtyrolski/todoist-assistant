package dev.mtyrolski.todoistassistant;

import org.json.JSONObject;

final class PlotHtml {
    private PlotHtml() {
    }

    static String render(JSONObject figure) {
        String json = figure == null ? "{}" : figure.toString().replace("</", "<\\/");
        return "<!doctype html><html><head>"
                + "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
                + "<style>html,body,#plot{margin:0;width:100%;height:100%;font-family:sans-serif;background:#fff;}</style>"
                + "<script src=\"https://cdn.plot.ly/plotly-2.35.2.min.js\"></script>"
                + "</head><body><div id=\"plot\"></div><script>"
                + "const figure=" + json + ";"
                + "Plotly.newPlot('plot', figure.data || [], figure.layout || {}, {responsive:true,displaylogo:false});"
                + "window.addEventListener('resize',()=>Plotly.Plots.resize('plot'));"
                + "</script></body></html>";
    }
}
