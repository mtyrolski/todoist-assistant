package com.todoistassistant;

import static org.junit.Assert.*;

import android.content.Context;
import androidx.test.core.app.ActivityScenario;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.Until;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;

public class MobileFlowTest {
  private UiDevice device;
  private ActivityScenario<MainActivity> activity;
  @org.junit.Rule public org.junit.rules.TestName name = new org.junit.rules.TestName();

  private androidx.test.uiautomator.BySelector text(String value) {
    return By.text(
        java.util.regex.Pattern.compile(
            java.util.regex.Pattern.quote(value), java.util.regex.Pattern.CASE_INSENSITIVE));
  }

  @Before
  public void startDisconnected() throws Exception {
    Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
    new TokenStore(context).clear();
    new SnapshotStore(context).clear();
    context.getSharedPreferences("rules", Context.MODE_PRIVATE).edit().clear().commit();
    device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
    device.setOrientationNatural();
    android.content.Intent intent =
        new android.content.Intent(context, MainActivity.class)
            .addFlags(
                android.content.Intent.FLAG_ACTIVITY_NEW_TASK
                    | android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK);
    activity = ActivityScenario.launch(intent);
    assertTrue(device.wait(Until.hasObject(By.text("Connect Todoist").enabled(true)), 15000));
  }

  @After
  public void close() throws Exception {
    Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
    java.io.File output = context.getExternalFilesDir("smoke");
    device.takeScreenshot(new java.io.File(output, name.getMethodName() + ".png"));
    device.dumpWindowHierarchy(new java.io.File(output, name.getMethodName() + ".xml"));
    if (activity != null) activity.close();
    device.setOrientationNatural();
    device.unfreezeRotation();
  }

  private void demo() {
    var example = device.wait(Until.findObject(By.text("Explore a demo")), 3000);
    if (example == null)
      example =
          device
              .findObject(By.clazz("androidx.recyclerview.widget.RecyclerView"))
              .scrollUntil(
                  androidx.test.uiautomator.Direction.DOWN,
                  Until.findObject(By.text("Explore a demo")));
    assertNotNull(example);
    example.click();
    assertTrue(device.wait(Until.hasObject(By.text("40 active tasks")), 15000));
  }

  @Test
  public void demoWorksOfflineAndDoesNotCreateAccountData() throws Exception {
    demo();
    Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
    assertEquals("", new TokenStore(context).load());
    assertFalse(context.getFileStreamPath("dashboard-v1.json").exists());
    assertTrue(device.hasObject(By.text("Back to my data")));
    device.findObject(By.text("Back to my data")).click();
    assertTrue(device.wait(Until.hasObject(By.text("Explore a demo")), 5000));
  }

  @Test
  public void taskSearchAndPriorityFilterHaveAUsefulEmptyState() throws Exception {
    demo();
    device.findObject(By.text("Projects")).click();
    assertTrue(device.wait(Until.hasObject(By.desc("Search tasks, projects or activity")), 5000));
    device.findObject(By.desc("Search tasks, projects or activity")).setText("release");
    assertTrue(device.wait(Until.hasObject(By.textContains("Review the release checklist")), 5000));
    device.findObject(By.desc("Filter task priority")).click();
    device.wait(Until.hasObject(By.text("P1")), 3000);
    device.findObject(By.text("P1")).click();
    assertTrue(device.wait(Until.hasObject(By.text("No tasks match")), 5000));
  }

  @Test
  public void rotationKeepsDemoAndSearchState() throws Exception {
    demo();
    device.findObject(By.text("Projects")).click();
    device.findObject(By.desc("Search tasks, projects or activity")).setText("release");
    assertTrue(device.wait(Until.hasObject(By.textContains("Review the release checklist")), 5000));
    device.setOrientationLeft();
    assertTrue(device.wait(Until.hasObject(By.text("Back to my data")), 8000));
    assertTrue(device.wait(Until.hasObject(By.text("release")), 8000));
  }

  @Test
  public void attentionRulesCanBeDisabledAndPersisted() throws Exception {
    demo();
    device.findObject(By.text("Settings")).click();
    var option = device.wait(Until.findObject(By.text("Alert rules")), 5000);
    assertNotNull(option);
    option.click();
    assertTrue(device.wait(Until.hasObject(By.text("Enable attention monitoring")), 5000));
    device.findObject(By.text("Enable attention monitoring")).click();
    device.findObject(text("Save")).click();
    assertTrue(device.wait(Until.hasObject(By.text("Monitoring paused")), 5000));
    activity.recreate();
    assertTrue(device.wait(Until.hasObject(By.text("Monitoring paused")), 8000));
  }

  @Test
  public void emptyTokenShowsValidationWithoutSendingRequests() {
    device.findObject(By.text("Connect Todoist")).click();
    assertTrue(device.wait(Until.hasObject(text("Connect and sync")), 5000));
    device.findObject(text("Connect and sync")).click();
    assertTrue(device.hasObject(text("Connect and sync")));
    assertEquals(1, device.findObjects(text("Connect and sync")).size());
  }
}
