# Notes for the handwritten reflection

This is not the submission PDF. Write at most three pages by hand, scan them, and save the scan as `230101098.pdf` in the project root. Put your name and roll number on the first page.

Name: Aaryan Kumar Sinha  
Roll number: 230101098  
GitHub: https://github.com/aaryansinhaa/cs3081-command-parser

Suggested pages:

1. What I learned. Sequence-level distillation means the student is trained on the teacher's text, not on the teacher's logits. A 70M model can copy a narrow JSON format even when the intent is sometimes wrong. Object storage, readiness probes, and a stateless NACL are separate ideas: the model is not in the image, traffic waits until `/readyz` is 200, and a reply packet needs its own rule because the NACL does not remember the request.

2. Challenges and how they were handled. The laptop has 16 GB of RAM and a 4 GB GPU, and port 8080 was already used by another project. Teacher labelling is slow enough that it had to start before the cluster. Python 3.14 cannot use the pinned CPU PyTorch wheel, so training uses Python 3.12. Failed teacher calls are recorded instead of being replaced with an empty reply. Fill this page with the actual failures you saw (Ollama download, memory, a pod that stayed unready, a cleaning rejection) once those runs exist. Do not invent numbers.

3. Findings and what to improve. Compare the teacher, the untrained Pythia model, and the trained student using the real `score.py` table. Say whether JSON validity was easier to learn than the slots. Note that one k3d node does not show failure of a machine. A useful improvement is a shorter teacher prompt or a constrained decoder if validity is the weak number, and a second k3d agent only if the laptop has the RAM. Mention that the handwritten pages and the technical report are different documents, and that model weights live in the GitHub Release.

Keep the handwriting yours. Do not paste an AI-written essay into the scan.
