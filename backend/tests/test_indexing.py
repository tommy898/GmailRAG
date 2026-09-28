import unittest
import uuid
from unittest.mock import MagicMock, call, patch

from app.indexing import (
    StoredChunk,
    embed_and_store_chunks,
    index_email,
    replace_email_chunks,
    upsert_embedding,
)


class IndexingTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor

    @patch("app.indexing.chunk_email")
    def test_replace_email_chunks_removes_stale_versions(self, chunk_email):
        email_id = uuid.uuid4()
        first_chunk_id = uuid.uuid4()
        second_chunk_id = uuid.uuid4()
        chunk_email.return_value = ["first chunk", "second chunk"]
        self.cursor.fetchone.side_effect = [
            (first_chunk_id,),
            (second_chunk_id,),
        ]

        stored_chunks = replace_email_chunks(
            self.connection,
            email_id,
            {"body_text": "message"},
        )

        delete_sql, delete_parameters = self.cursor.execute.call_args_list[0].args
        normalized_delete_sql = " ".join(delete_sql.split())
        self.assertEqual(
            normalized_delete_sql,
            "delete from email_chunks where email_id = %s",
        )
        self.assertEqual(delete_parameters, (email_id,))
        self.assertNotIn("chunker_version", normalized_delete_sql)
        self.assertEqual(
            stored_chunks,
            [
                StoredChunk(first_chunk_id, "first chunk"),
                StoredChunk(second_chunk_id, "second chunk"),
            ],
        )

    @patch("app.indexing.upsert_embedding")
    @patch("app.indexing.embed_texts")
    def test_embed_and_store_chunks_uses_stored_chunk_ids(
        self,
        embed_texts,
        upsert_embedding,
    ):
        first_chunk = StoredChunk(uuid.uuid4(), "first chunk")
        second_chunk = StoredChunk(uuid.uuid4(), "second chunk")
        first_embedding = [0.1, 0.2]
        second_embedding = [0.3, 0.4]
        embed_texts.return_value = [first_embedding, second_embedding]

        embedded_count = embed_and_store_chunks(
            self.connection,
            [first_chunk, second_chunk],
        )

        self.assertEqual(embedded_count, 2)
        embed_texts.assert_called_once_with(["first chunk", "second chunk"])
        upsert_embedding.assert_has_calls(
            [
                call(self.connection, first_chunk.id, first_embedding),
                call(self.connection, second_chunk.id, second_embedding),
            ]
        )

    @patch("app.indexing.embed_texts")
    def test_embed_and_store_chunks_skips_empty_input(self, embed_texts):
        self.assertEqual(embed_and_store_chunks(self.connection, []), 0)
        embed_texts.assert_not_called()

    @patch("app.indexing.embed_and_store_chunks")
    @patch("app.indexing.replace_email_chunks")
    def test_index_email_coordinates_chunking_and_embedding(
        self,
        replace_email_chunks,
        embed_and_store_chunks,
    ):
        email_id = uuid.uuid4()
        email = {"body_text": "message"}
        stored_chunks = [StoredChunk(uuid.uuid4(), "chunk")]
        replace_email_chunks.return_value = stored_chunks

        chunk_count = index_email(self.connection, email_id, email)

        self.assertEqual(chunk_count, 1)
        replace_email_chunks.assert_called_once_with(
            self.connection,
            email_id,
            email,
        )
        embed_and_store_chunks.assert_called_once_with(
            self.connection,
            stored_chunks,
        )

    @patch("app.indexing.embed_and_store_chunks")
    @patch("app.indexing.replace_email_chunks")
    def test_index_email_can_defer_embedding(
        self,
        replace_email_chunks,
        embed_and_store_chunks,
    ):
        stored_chunks = [StoredChunk(uuid.uuid4(), "chunk")]
        replace_email_chunks.return_value = stored_chunks

        chunk_count = index_email(
            self.connection,
            uuid.uuid4(),
            {"body_text": "message"},
            embed_chunks=False,
        )

        self.assertEqual(chunk_count, 1)
        embed_and_store_chunks.assert_not_called()

    @patch("app.indexing.embedding_to_pgvector")
    def test_embedding_retry_updates_instead_of_duplicating(
        self,
        embedding_to_pgvector,
    ):
        embedding_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        embedding = [0.0] * 384
        embedding_to_pgvector.return_value = "[vector]"
        self.cursor.fetchone.return_value = (embedding_id,)

        result = upsert_embedding(self.connection, chunk_id, embedding)

        self.assertEqual(result, embedding_id)
        sql, parameters = self.cursor.execute.call_args.args
        normalized_sql = " ".join(sql.split())
        self.assertIn(
            "on conflict (chunk_id, embedding_model) do update",
            normalized_sql,
        )
        self.assertEqual(parameters[0], chunk_id)


if __name__ == "__main__":
    unittest.main()
