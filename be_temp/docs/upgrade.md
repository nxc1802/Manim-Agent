Proposal: Nâng cấp Manim Agent với 3B1B Primitive Runtime + Manim Docs Error-RAG Reviewer

⸻

Executive Summary

Mục tiêu:

Biến Manim Agent từ:

Prompt → Code Generation

thành:

Retrieval + Primitive + Runtime-Grounded Code Synthesis

⸻

Hai nâng cấp chiến lược:

1. Primitive Mode V2

Dùng hệ sinh thái 3b1b/manimlib như “visual primitive substrate”

Thay vì tự build primitive catalog từ đầu.

2. RAG Reviewer Mode

Parse lỗi từ render logs → retrieve đúng docs/snippets → feed cho Code Reviewer

Thay vì reviewer sửa lỗi bằng prior knowledge thuần LLM.

⸻

⸻

PART I — Primitive Mode V2

“Adopt, Wrap, Abstract — Don’t Reinvent”

⸻

Vấn đề hiện tại

Primitive hiện tại trong dự án:

Ưu điểm:

* Clean
* Controlled
* Dễ parameterize

Nhược điểm:

* Primitive depth thấp
* Coverage hạn chế
* Thiếu advanced animation grammar
* Mất rất nhiều thời gian mở rộng

⸻

Insight:

3B1B manimlib = primitive super-library đã battle-tested

⸻

Manimlib có sẵn:

Scene grammar:

* TransformMatchingTex
* LaggedStart
* AnimationGroup
* ValueTracker
* always_redraw
* ComplexPlane
* GraphScene-like structures
* NumberPlane
* Coordinate systems
* Advanced camera choreography
* Mathematical exposition patterns

⸻

Đề xuất:

Không dùng manimlib như raw engine.

Dùng nó như:

Primitive Source Layer

⸻

Kiến trúc mới:

3B1B manimlib
    ↓
Primitive Wrapper Layer
    ↓
Normalized Internal Primitive Schema
    ↓
Planner / Builder

⸻

Ví dụ:

Raw:

TransformMatchingTex(eq1, eq2)

Wrapped:

{
  "primitive": "equation_morph",
  "source": "3b1b",
  "args": {...}
}

⸻

Lợi ích:

1. Không lock-in vào 3B1B syntax

2. Có abstraction layer

3. Có thể fallback sang community Manim

4. Reviewer dễ validate

⸻

Primitive Taxonomy đề xuất:

Tier 1 — Core Layout

* title_card
* bullet_reveal
* panel_split

Tier 2 — Mathematical Exposition

* transform_matching_equation
* graph_plot
* axis_reveal
* theorem_build

Tier 3 — Cinematic

* focus_zoom
* progressive_highlight
* camera_pan_math

Tier 4 — Domain Specific

* neural_net_forward
* binary_tree_walk
* sorting_trace

⸻

Implementation Steps

Phase A — Primitive Mining

Parse manimlib:

* animation/
* mobject/
* scene/
* once_useful_constructs/

⸻

Phase B — Wrapper Generation

Build:

primitives_3b1b_registry.yaml

Schema:

primitive_name:
  source_function:
  required_args:
  optional_args:
  compatible_with:
  example:

⸻

Phase C — Builder Integration

Builder logic:

If task == advanced_math:
→ prefer 3b1b primitive

Else:
→ use local primitive

⸻

Risks:

1. manimlib != community manim

Fix:

Compatibility Adapter Layer

⸻

2. API mismatch

Fix:

Auto transpiler:
3b1b syntax → community syntax

⸻

Expected Impact:

Primitive count:

27 → 150+

Builder reliability:

+35–50%

Visual sophistication:

+60%

⸻

⸻

PART II — Error-RAG Reviewer Mode

“Logs are queries”

⸻

Current Problem:

Code Reviewer hiện:

Error → LLM guesses fix

⸻

Failure:

* hallucinated imports
* wrong syntax
* outdated API
* repeated loops

⸻

New Concept:

Render Log becomes Retrieval Query

⸻

Pipeline:

Render Fail
   ↓
Log Parser
   ↓
Error Classifier
   ↓
RAG Query Generator
   ↓
Manim Docs Retrieval
   ↓
Snippet + Explanation
   ↓
Code Reviewer Fix

⸻

Ví dụ:

Log:

AttributeError: 'Scene' object has no attribute 'play_text'

⸻

Parse:

Error Type:

AttributeError

Symbol:

play_text

⸻

Query:

Manim Community Scene methods play Write FadeIn

⸻

Retrieve:

* Scene.play docs
* Write()
* Text()

⸻

Reviewer Prompt:

“Replace invalid play_text with self.play(Write(Text(...)))”

⸻

Data Sources Priority:

Tier 1:

Official Docs

https://docs.manim.community/en/stable/

Tier 2:

Reference Manual

API objects

Tier 3:

Community examples

Tier 4:

Internal fix history

⸻

Retrieval Granularity:

Best:

Symbol + Error + Version

⸻

Example Index:

Scene.play
MathTex
TransformMatchingTex
Axes.plot
always_redraw

⸻

RAG Components

A. Log Parser

Regex:

* AttributeError
* TypeError
* ImportError
* ValueError
* Latex compilation error

⸻

B. Error Ontology

AttributeError:
  likely_causes:
    - wrong method
    - deprecated API

⸻

C. Vector Store

Chunking:

Recommended:

Function-level docs sections (200–500 tokens)

⸻

Why function-level?

Too coarse:

Whole page → noisy

Too fine:

Single line → loses context

⸻

Reviewer Prompt Upgrade:

Before:

“Fix this code.”

After:

“Fix using retrieved official docs below.”

⸻

Expected Results:

First-pass fix accuracy:

+40–70%

Retry loop rounds:

-30–50%

Hallucination:

Major drop

⸻

⸻

PART III — Unified Architecture

User Prompt
   ↓
Director
   ↓
Planner
   ↓
Primitive Selector
   ├─ Local Primitive
   └─ 3B1B Primitive
   ↓
Builder
   ↓
Render
   ↓
If Error:
   Log Parser
   ↓
Docs RAG
   ↓
Reviewer
   ↓
Builder Fix

⸻

PART IV — New File Structure

primitives/
 ├── local_registry.py
 ├── manimlib_adapter.py
 ├── primitive_selector.py
 └── 3b1b_registry.yaml
rag/
 ├── log_parser.py
 ├── error_taxonomy.py
 ├── docs_indexer.py
 ├── retriever.py
 └── reviewer_context_builder.py

⸻

PART V — KPI

Metric	Current	Target
Primitive Coverage	27	150+
First-pass compile success	~?	+30%
Review rounds avg	High	-40%
Visual sophistication	Medium	High
Reviewer hallucination	Medium	Low

⸻

PART VI — Strategic Advantage

Without this:

AI Manim generator = commodity

With this:

Runtime-informed visual compiler

⸻

Final Recommendation

PRIORITY 1:

Error-RAG Reviewer

Vì dễ triển khai, ROI cao, giảm lỗi ngay.

⸻

PRIORITY 2:

3B1B Primitive Integration

Vì đây là moat dài hạn.

⸻

Guiding Principle:

“Generate less. Retrieve more. Reuse proven visual grammar.”

⸻

One-line Strategy:

Borrow 3Blue1Brown’s visual intelligence, then augment it with retrieval-grounded self-correction.