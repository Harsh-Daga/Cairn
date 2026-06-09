---
description: Synthesize summaries with the project spec.
---
Using the summaries and spec below, write a cohesive synthesis (3–5 short paragraphs).

{% for s in summaries %}
## {{ s.stem }}
{{ s.content }}
{% endfor %}

<spec>
{{ spec }}
</spec>
