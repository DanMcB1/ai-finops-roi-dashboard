# Demo script (~1 minute)

A talk track you can say out loud in an interview. Plain language. Practice it once with the app open on the default November view. You do not need to memorize it word for word.

**Setup:** `streamlit run app.py` is already running. Leave the date range on **This month (Nov 2026)**. You will point at the exec summary, then at one or two numbers — Service hours, the F&I cost-per-task rise, and the Marketing spike.

---

## The talk track

“In a dealership, nobody manages the business from one company total. You look at F&I gross, service absorption, sales by store. When a group rolls out AI, they need the same view: what did each department spend, and what did they get back?

This is a sample FinOps dashboard for a mid-size dealer group. It’s demo data — I’m not connected to a live billing API — but the shape is the conversation I’d have after a rollout, not before one.

Up top is a plain-English summary the app writes from the numbers, not from a chatbot. This month, the group has spent about eight thousand four hundred against a twelve-thousand-dollar budget. That’s roughly three hundred and eighty-five hours saved, about nineteen thousand dollars of time at loaded rates, or a little over 2x the spend. Service saved the most time. F&I cost per task is up about fifty percent this week, because they shifted more work onto a more expensive model. And Marketing has a spike on November 18 — about six times their usual daily spend — which the dashboard flags with a simple rule: any day over twice the last seven-day average.

I can change the hourly rates or the price assumptions in the sidebar and the whole picture recalculates, and I can export a showback table for finance. I want to be honest: time saved here is an estimate, and this ROI does not include F&I gross or CSI. It’s a starting point for a conversation, not a close-the-books number.”

---

## Timing notes

Spoken at a normal pace, that is about 50–60 seconds. If you have a few extra seconds, click **Anomalies** or the Marketing line on the spend chart and say: “I’d ask Marketing what ran that day before I called it a problem — a campaign can look like a spike.” Then stop and let them ask questions.

## If they ask a follow-up

- **“Are these real prices?”**  
  “No. They’re labeled as illustrative, fully loaded unit costs — a little token cost plus an allocated platform share. I made them editable on purpose. In a real engagement I’d plug in the customer’s actual contract rates, and I’d be clear what is usage and what is allocated.”

- **“How do you know hours were actually saved?”**  
  “In this demo, I don’t. Each row has an estimated minutes field so the math is visible. On a real account I’d want a baseline from week 1 of the SOW — timestamps, a sample of write-ups, or a before/after — and I’d say so if we didn’t have one.”

- **“Why not include PVR or gross in the ROI?”**  
  “I would, once we had a clean baseline and the customer agreed the tool could be tied to it. I didn’t invent a PVR lift here because I haven’t earned that number. Time value is the conservative version of the story.”

- **“What’s the anomaly rule?”**  
  “If a day’s spend is more than twice the average of the previous seven days, it gets flagged. It’s meant to start a question, not to accuse anyone. November 18 is a Marketing campaign-style spike in the sample.”

- **“What would production look like?”**  
  “Pull real usage and invoices from the vendors, SSO so each director sees their department, cost-allocation tags down to the store, and a showback that finance can actually journal. Plus the outcome metrics we scoped up front — not just minutes.”
