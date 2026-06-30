package dev.mtyrolski.todoistassistant;

import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;

import org.json.JSONObject;

import java.net.URLEncoder;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class BackgroundAutomationJobService extends JobService {
    private static final int JOB_ID = 42031;
    private ExecutorService executor;

    static void schedule(Context context, int intervalMinutes) {
        ComponentName component = new ComponentName(context, BackgroundAutomationJobService.class);
        JobInfo job = new JobInfo.Builder(JOB_ID, component)
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPersisted(true)
                .setPeriodic(Math.max(AppSettings.MIN_PERIODIC_MINUTES, intervalMinutes) * 60L * 1000L)
                .build();
        JobScheduler scheduler = (JobScheduler) context.getSystemService(Context.JOB_SCHEDULER_SERVICE);
        if (scheduler != null) {
            scheduler.schedule(job);
        }
    }

    static void cancel(Context context) {
        JobScheduler scheduler = (JobScheduler) context.getSystemService(Context.JOB_SCHEDULER_SERVICE);
        if (scheduler != null) {
            scheduler.cancel(JOB_ID);
        }
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        executor = Executors.newSingleThreadExecutor();
        executor.execute(() -> {
            boolean retry = false;
            try {
                AppSettings settings = new AppSettings(this);
                ApiClient client = new ApiClient(settings.serverUrl());
                String automation = settings.automation();
                String path = "ALL".equalsIgnoreCase(automation)
                        ? "/api/admin/automations/run_all_async"
                        : "/api/admin/automations/run_async?name=" + urlEncode(automation);
                client.post(path, new JSONObject());
            } catch (Exception exc) {
                retry = true;
            } finally {
                jobFinished(params, retry);
            }
        });
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        if (executor != null) {
            executor.shutdownNow();
        }
        return true;
    }

    private static String urlEncode(String value) {
        try {
            return URLEncoder.encode(value, "UTF-8");
        } catch (Exception exc) {
            return value;
        }
    }
}
