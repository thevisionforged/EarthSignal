# EarthSignal: presenter's guide (no science background needed)

This guide is for whoever presents EarthSignal. Every number below comes from the app itself. If you are asked something not covered here, it is fine to say "that's outside what we measured".

## The 30-second pitch
Lucknow has 45 years of free NASA weather data, but raw data doesn't tell anyone what's changed or which events mattered. EarthSignal turns that record into four things:
1. **What has (and hasn't) changed:** honest trend tests on temperature and rainfall, including saying "no trend" when that's the answer.
2. **What if:** a studio to explore "what if every day were 2 °C warmer?"
3. **What happened, and was it real:** a workflow that finds extreme events, checks them against other sources, and records an analyst's decision.
4. **What's coming:** a temperature outlook for the next few weeks, shown only because it passed a fair test set in advance.

Our edge is **trust**: every number traces back to a stored NASA download, and the app is open about what it doesn't know.

## Words you'll need
| Term | Plain meaning |
|---|---|
| NASA POWER | A free NASA service giving daily weather estimates for any spot on Earth, from 1981. |
| Reanalysis | A computer model's best reconstruction of past weather, constrained by real measurements. An *estimate*, not a thermometer reading. |
| Grid cell | POWER gives one value per box about 55 × 62 km. Lucknow sits on the border of two boxes, so we show both. |
| Weather station | A real thermometer at Lucknow airport (NOAA data). Used as an independent check. |
| IMERG | NASA satellite rainfall estimates. A second, independent opinion on rain. |
| IMD | India Meteorological Department's rain-gauge map. The closest thing to "ground truth" for rainfall. |
| Percentile | "95th percentile" = hotter than 95 out of 100 comparable days. |
| Hypothetical | A what-if calculation, not a prediction. |

## Tour of the app (about 5 minutes)
1. **Key findings:**
   - **Temperature:** there is **no significant trend** for 1981–2025 in either cell. A naive test would wrongly report "significant cooling"; ours corrects for that, and shows that the answer changes depending on which start year you pick.
   - **Rainfall:** NASA POWER's apparent rainfall rise is **not supported by rain gauges**. POWER drifts away from the Indian gauge map (IMD) from 2006 onward, while NASA's satellite estimate (IMERG) stays in line with the gauges. Say: *"We don't claim a rainfall trend for Lucknow."*
   - **Why this matters:** most dashboards would have shown a trend. Ours tells you when the data can't support one.
2. **Simulation Studio:** pick "warmer +2 °C". Days with a daily-average temperature above 35 °C go from about **44 to 70 a year**. Say: *"This is a what-if on past data, not a forecast."*
3. **Response Intelligence:** the three steps are shown at the top of the page.
   - **Detect:** the app found **77 heat episodes** and **47 extreme rainfall events** in the city-centre cell since 1981.
   - **Investigate:** click the top heat episode, **19–30 July 2002**. The airport station agrees it was unusual (4 of 5 days with full records). Then click the top rainfall event, **29–30 Aug 2000** (282 mm). Neither satellite nor rain gauges confirm it, so the app warns *it may be a data artifact*.
   - **Respond:** open a case, type a reason, click a decision, and download the evidence brief. Every action is logged.

4. **Anticipate:** the temperature outlook for the next weeks, with a shaded 90% range.
   - Point at the chart: the forecast line bends back towards the dotted "usual" line within about two weeks. Say: *"After a couple of weeks, nobody can beat the seasonal average with past temperatures alone, and our chart shows that honestly."*
   - Scroll to **How we know it works**: we wrote the test down first, then the forecast had to beat the best simple method on 12 years it had never seen. It passed, by a modest 2–7%.

**The line to land:** *"Our system didn't just flag the biggest rainstorm. It caught that the storm might not have happened. That's the difference between data and intelligence."*

## Likely questions and honest answers
- **"Can it predict the weather?"** It gives a statistical temperature outlook for the next few weeks, and only because it passed a test we wrote down in advance. It's modestly better than the best simple method, mostly in the first week. It does not predict rain, and it's not a replacement for IMD's official forecasts.
- **"Is this used for public warnings?"** No. It's an analyst's tool. Warnings need real-time data and official authority.
- **"Why trust it?"** Raw data is stored unchanged; every result shows its source, version and method; 218 automated tests (184 backend + 34 frontend) check the calculations.
- **"What does it cost to run?"** It runs on a laptop with free public data. No cloud or paid services.
- **"What's next?"** Checking each issued outlook once NASA's data for those days arrives, more cities, more variables (air quality, humidity).

## Things NOT to say
- Don't call the NASA data "observations" or "measurements". Say "estimates" or "reanalysis".
- Don't claim health, flood, crop or money impacts. The app deliberately doesn't calculate them.
- Don't say "this will happen" about any simulation. Say "if… then, in the past record…".
- Don't call the outlook "the weather forecast" or say it predicts rain. Say "a statistical temperature outlook"; IMD's official forecast comes first.
- Don't say an event is "once in 46 years" as a probability. Say "it happened in 1 of 46 years of this record".
