"""Tests for data models and JSON store."""

import tempfile
import unittest
from pathlib import Path

from ytauto.models.job import Job, JobStatus, PipelineStep, StepStatus, VideoMetadata
from ytauto.store.json_store import JsonDirectoryStore


class TestJobModel(unittest.TestCase):
    def test_job_creation_defaults(self):
        job = Job(topic="Test Topic")
        self.assertTrue(job.id.startswith("job_"))
        self.assertEqual(job.topic, "Test Topic")
        self.assertEqual(job.status, JobStatus.created)
        self.assertEqual(job.duration_config, "medium")
        self.assertEqual(job.voice_config, "onyx")
        self.assertEqual(job.engine_config, "claude")
        self.assertIsNotNone(job.created_at)

    def test_job_touch(self):
        job = Job(topic="Test")
        old_updated = job.updated_at
        job.touch()
        self.assertGreaterEqual(job.updated_at, old_updated)

    def test_pipeline_step_defaults(self):
        step = PipelineStep(name="test_step")
        self.assertEqual(step.status, StepStatus.pending)
        self.assertIsNone(step.started_at)
        self.assertIsNone(step.error)
        self.assertEqual(step.outputs, [])

    def test_video_metadata_defaults(self):
        meta = VideoMetadata()
        self.assertEqual(meta.title, "")
        self.assertEqual(meta.privacy, "private")
        self.assertEqual(meta.category_id, "22")


class TestJsonDirectoryStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = JsonDirectoryStore[Job](Path(self.tmpdir), Job)

    def test_save_and_get(self):
        job = Job(topic="Store Test")
        self.store.save(job)

        loaded = self.store.get(job.id)
        self.assertEqual(loaded.id, job.id)
        self.assertEqual(loaded.topic, "Store Test")
        self.assertEqual(loaded.status, JobStatus.created)

    def test_list_all(self):
        j1 = Job(topic="First")
        j2 = Job(topic="Second")
        self.store.save(j1)
        self.store.save(j2)

        all_jobs = self.store.list_all()
        self.assertEqual(len(all_jobs), 2)

    def test_delete(self):
        job = Job(topic="Delete Me")
        self.store.save(job)
        self.assertTrue(self.store.delete(job.id))
        with self.assertRaises(FileNotFoundError):
            self.store.get(job.id)

    def test_get_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.store.get("nonexistent")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
