"use client";

import { useEffect, useState } from "react";
import { HistoryDashboard } from "../components/DashboardView";
import styles from "./calendar.module.css";

const DAY = 86_400_000;
const FIRST_YEAR = 2000;
const MAX_DAYS = 260 * 7;
const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const monthName = new Intl.DateTimeFormat("en", { month: "long", timeZone: "UTC" });
const dayName = new Intl.DateTimeFormat("en", { dateStyle: "full", timeZone: "UTC" });
const shortDate = new Intl.DateTimeFormat("en", { dateStyle: "medium", timeZone: "UTC" });
const months = Array.from({ length: 12 }, (_, month) => monthName.format(Date.UTC(2000, month)));

type DateRange = { beg: string; end: string };

function dayKey(time: number) {
  return new Date(time).toISOString().slice(0, 10);
}

function weekNumber(monday: number) {
  const thursday = new Date(monday + 3 * DAY);
  return Math.floor((thursday.getTime() - Date.UTC(thursday.getUTCFullYear(), 0)) / (7 * DAY)) + 1;
}

export default function ActivityHistoryPage() {
  const [today, setToday] = useState("");
  const [month, setMonth] = useState(0);
  const [draft, setDraft] = useState<DateRange>({ beg: "", end: "" });
  const [applied, setApplied] = useState<DateRange | null>(null);

  useEffect(() => {
    const now = new Date();
    setToday(dayKey(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())));
    setMonth(Date.UTC(now.getFullYear(), now.getMonth()));
  }, []);

  const [currentYear, currentMonth] = today.split("-").map(Number);
  const latestMonth = Date.UTC(currentYear, currentMonth - 1);
  const cursor = new Date(month);
  const year = cursor.getUTCFullYear();
  const monthIndex = cursor.getUTCMonth();
  const nextMonth = Date.UTC(year, monthIndex + 1);
  const firstMonday = month - ((cursor.getUTCDay() + 6) % 7) * DAY;
  const weekStarts = Array.from({ length: Math.ceil((nextMonth - firstMonday) / (7 * DAY)) }, (_, i) => firstMonday + i * 7 * DAY);
  const days = (Date.parse(draft.end) - Date.parse(draft.beg)) / DAY + 1;
  const entireRange = Boolean(draft.beg && draft.end);
  const valid = entireRange && days > 0 && days <= MAX_DAYS && draft.end <= today;

  const selectPeriod = (start: number, end: number) => {
    const last = dayKey(end);
    setDraft({ beg: dayKey(start), end: last < today ? last : today });
  };

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>Activity History</h1>
          <p className="lede">Choose a period to explore your locally saved activity.</p>
        </div>
      </header>
      {today ? (
        <form
          className={`card ${styles.picker}`}
          onSubmit={(event) => {
            event.preventDefault();
            if (valid) setApplied({ ...draft });
          }}
        >
          <section aria-labelledby="history-calendar-title">
            <h2 id="history-calendar-title">Calendar</h2>
            <div className={styles.controls}>
              <button className="button buttonGhost buttonSmall" type="button" aria-label="Previous month"
                disabled={month <= Date.UTC(FIRST_YEAR, 0)} onClick={() => setMonth(Date.UTC(year, monthIndex - 1))}>←</button>
              <label>
                <span className="muted tiny">Month</span>
                <select className="select" value={monthIndex} onChange={(event) => setMonth(Date.UTC(year, Number(event.target.value)))}>
                  {months.map((name, index) => <option key={name} value={index} disabled={Date.UTC(year, index) > latestMonth}>{name}</option>)}
                </select>
              </label>
              <label>
                <span className="muted tiny">Year</span>
                <select className="select" value={year} onChange={(event) => setMonth(Math.min(Date.UTC(Number(event.target.value), monthIndex), latestMonth))}>
                  {Array.from({ length: currentYear - FIRST_YEAR + 1 }, (_, index) => currentYear - index)
                    .map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </label>
              <button className="button buttonGhost buttonSmall" type="button" aria-label="Next month"
                disabled={nextMonth > latestMonth} onClick={() => setMonth(nextMonth)}>→</button>
            </div>
            <table className={styles.calendar} aria-label={`${months[monthIndex]} ${year}`}>
              <thead><tr><th scope="col">Week</th>{weekdays.map((name) => <th scope="col" key={name}>{name}</th>)}</tr></thead>
              <tbody>
                {weekStarts.map((week) => (
                  <tr key={week}>
                    <th scope="row">
                      <button className={styles.period} type="button" aria-label={`Select week of ${shortDate.format(week)}`}
                        disabled={dayKey(week) > today}
                        onClick={() => selectPeriod(week, week + 6 * DAY)}>{weekNumber(week)}</button>
                    </th>
                    {weekdays.map((name, index) => {
                      const day = week + index * DAY;
                      const key = dayKey(day);
                      const selected = key >= draft.beg && key <= draft.end;
                      return (
                        <td key={name}>
                          <button className={styles.day} type="button" aria-label={dayName.format(day)}
                            aria-pressed={selected} aria-current={key === today ? "date" : undefined}
                            data-outside={day < month || day >= nextMonth} disabled={key > today}
                            onClick={() => selectPeriod(day, day)}>{new Date(day).getUTCDate()}</button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className={styles.range} aria-labelledby="history-range-title">
            <h2 id="history-range-title">Date range</h2>
            <div className={styles.shortcuts}>
              <button type="button" className="button buttonGhost buttonSmall" onClick={() => selectPeriod(month, nextMonth - DAY)}>Select month</button>
              <button type="button" className="button buttonGhost buttonSmall" onClick={() => selectPeriod(Date.UTC(year, 0), Date.UTC(year + 1, 0) - DAY)}>Select year</button>
            </div>
            <label className="control">
              <span className="muted tiny">From date</span>
              <input className="dateInput" type="date" max={today} value={draft.beg} onChange={(event) => setDraft({ ...draft, beg: event.target.value })} />
            </label>
            <label className="control">
              <span className="muted tiny">To date</span>
              <input className="dateInput" type="date" max={today} value={draft.end} onChange={(event) => setDraft({ ...draft, end: event.target.value })} />
            </label>
            <p className="muted tiny" aria-live="polite">
              {!entireRange ? "Pick a day, week, month or year, or enter both dates."
                : days <= 0 ? "The end date must be on or after the start date."
                : days > MAX_DAYS ? "Choose a range of up to 260 weeks."
                : draft.end > today ? "Choose dates through today."
                : `${days} ${days === 1 ? "day" : "days"} selected.`}
            </p>
            <button className="button" type="submit" disabled={!valid}>Load charts</button>
          </section>
        </form>
      ) : null}
      {applied ? <HistoryDashboard range={applied} /> : null}
    </>
  );
}
