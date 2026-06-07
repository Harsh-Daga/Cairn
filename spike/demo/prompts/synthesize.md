---
description: Synthesize all summaries with the spec into one brief.
---
Using the spec and the summaries below, write a single executive brief (≤200 words).

<spec>
{{ spec }}
</spec>

{% for s in summaries %}
<summary file="{{ s.stem }}">
{{ s.content }}
</summary>
{% endfor %}
