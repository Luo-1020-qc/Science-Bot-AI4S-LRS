"""Small public fixture for the G1 project-question acceptance run."""
FEATURE_GRID = 5
ALPHA = 1.0


def predict_mean(values):
    if not values:
        raise ValueError("values must not be empty")
    return sum(values) / len(values)
