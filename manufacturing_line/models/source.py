from dataclasses import dataclass
from numbers import Number
from typing import Optional, Union

import simpy

from manufacturing_line import distributions as dist
from manufacturing_line import failures as fail
from manufacturing_line.status import Status
from manufacturing_line._reports import SourceReport
from .base import Model



@dataclass
class Source(Model):
    name : str
    processing_time : Union[dist.Distribution, Number]
    output_buffer : str
    failure : Optional[fail.Failure] = None


    def _before_run(self, env:simpy.Environment, objects:dict):
        
        # Properties
        self._output_buffer = objects[self.output_buffer]
        self.processing_time = dist._create_dist(self.processing_time)

        # Tracking Stats
        self.time_blocked = 0
        self.time_broken = 0
        self.time_processing = 0

        # Micromanagement stats
        self.process_stats = 0
        self.processing_start_time = 0
        self.blocking_start_time = 0
        self.failure_start_time = 0
        self.status = Status.PROCESSING
        self.process_stats = []
        self.part = None

        # Environment
        self.env = env
        self.process = self.env.process(self._run_process())

        # Failure
        if isinstance(self.failure, fail.Failure):
            self.tbf = dist._create_dist(self.failure.time_between_failures)
            self.ttr = dist._create_dist(self.failure.time_to_repair)
            env.process(self._run_failure())


    def _run_process(self):
        while True:
            try:

                # Processing
                if self.status == Status.PROCESSING:
                    self._before_processing()
                    yield self.env.timeout(self.processing_time.generate())
                    self._after_processing()

                # Blocked
                elif self.status == Status.BLOCKED:
                    self._before_blocking()
                    yield self._output_buffer._buffer.put(self.part)
                    self._after_blocking()

            # Failure
            except simpy.Interrupt:
                self._before_failing()
                yield self.env.timeout(self.ttr.generate())
                self._after_failing()


    def _run_failure(self):
        while True:
            yield self.env.timeout(self.tbf.generate())
            self.process.interrupt()


    def _before_processing(self):
        self.processing_start_time = self.env.now
        

    def _after_processing(self):
        self.part = 1
        process_duration = self.env.now - self.processing_start_time
        self.time_processing += process_duration
        self.process_stats.append(process_duration)
        self.status = Status.BLOCKED


    def _before_blocking(self):
        self.blocking_start_time = self.env.now
        

    def _after_blocking(self):
        self.part = None
        self.time_blocked += (self.env.now-self.blocking_start_time)
        self.status = Status.PROCESSING


    def _before_failing(self):
        self.failure_start_time = self.env.now
        self._add_current_status()


    def _after_failing(self):
        self.time_broken += (self.env.now-self.failure_start_time)


    def _after_run(self):
        self.items_processed = len(self.process_stats)
        self._add_current_status()

        try:
            self.average_processing_time = self.time_processing / self.items_processed
        except ZeroDivisionError:
            self.average_processing_time = 0

        # Clear micromanagement stats
        del self.part
        del self.process_stats
        del self.processing_start_time
        del self.blocking_start_time
        del self.failure_start_time


    def _add_current_status(self):
        if self.status == Status.PROCESSING:
            self.time_processing += (self.env.now-self.processing_start_time)
        elif self.status == Status.BLOCKED:
            self.time_broken += (self.env.now-self.blocking_start_time)


    @property
    def report(self) -> str:
        return SourceReport(self)
