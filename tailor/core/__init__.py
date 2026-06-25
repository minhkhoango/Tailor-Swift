"""The deterministic core of the tailor program.

Everything in here is mechanical and model-free: LaTeX parsing, slot-file schema +
assembly, pdflatex compile, 1-page fit measurement, the number-traceability honesty
check, and the combined chain that runs them. The orchestrator (``tailor``) drives
the model and calls into this package; this package never calls the model.
"""
