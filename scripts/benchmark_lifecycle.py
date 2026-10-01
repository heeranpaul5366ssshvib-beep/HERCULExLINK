"""Benchmark startup + request latency (no chain-of-thought printed)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.initializer import RuntimeInitializer


def main():
    t0 = time.perf_counter()
    services = RuntimeInitializer().initialize()
    startup_ms = (time.perf_counter() - t0) * 1000.0
    brain = services["brain"]

    t0 = time.perf_counter()
    brain.think("hi")
    think_ms = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    task_report = brain.run_cycle("calculate 25 * 4")
    task_ms = (time.perf_counter() - t0) * 1000.0

    print(f"startup_ms={startup_ms:.1f}")
    print(f"think_hi_ms={think_ms:.1f}")
    print(f"task_calculate_ms={task_ms:.1f} status={task_report.get('status')}")
    print(f"task_latency_ms={task_report.get('latency_ms')} "
          f"verified={task_report.get('verification', {}).get('passed_steps')}")


if __name__ == "__main__":
    main()
