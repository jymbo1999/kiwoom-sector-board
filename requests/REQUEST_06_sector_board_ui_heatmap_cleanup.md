# REQUEST 06 - Sector Board UI Heatmap Cleanup

## Goal

Refine the Streamlit dashboard UI for rise-reason summaries, featured themes, sector history, and treemap readability.

## Requested changes

- Show rise-reason stock cells as `name (change rate)` on the first line and ticker on the second line.
- Apply a yellow-to-red heatmap to change-rate badges, with the lowest value yellow and the highest value red.
- Remove separate ticker/change-rate columns from the rise-reason table.
- Move the sector column before the stock-name column.
- Give the rise-reason summary column the largest width.
- Merge confidence badges into the evidence-title column.
- Apply the same change-rate heatmap to today's featured theme leaders.
- Use the same sector colors for today's featured theme boxes and the date-by-date sector history.
- Replace dark, similar-looking sector history colors with more distinguishable colors.
- Add click-to-focus behavior to sector history cells: selected sector stays vivid, other sector cells dim; clicking again clears the focus.
- Remove the recent date-by-date theme-flow table.
- Remove the selected-theme leader table.
- Add individual leader change rates to treemap labels.
- Change treemap heatmap semantics to Korean market colors: red for 상승 and blue for 하락.
