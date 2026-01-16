# Log-gap audit

Goal: if the diagram cannot be built confidently, output a report saying **exactly what is missing**.

Examples of gaps:
- request payload not logged at boundary
- response payload not logged
- no stable correlation id between component A and B
- retry attempt number not logged

The report should say:
- which component
- which operation
- which field(s)
- suggested minimal code/log change
