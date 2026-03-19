"""Entry point for real-data bootstrap."""
from services.worker.app.bootstrap import bootstrap_real_data_flow

if __name__ == "__main__":
    print(bootstrap_real_data_flow())
