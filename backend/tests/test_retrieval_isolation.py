import unittest
import uuid
from unittest.mock import MagicMock, patch

from app.embeddings import EMBEDDING_MODEL
from app.rag import answer_question
from app.retrieval import retrieve_chunks


class RetrievalIsolationTests(unittest.TestCase):
    @patch("app.retrieval.get_connection")
    @patch("app.retrieval.embedding_to_pgvector")
    @patch("app.retrieval.embed_text")
    def test_retrieval_filters_by_authenticated_profile(
        self,
        embed_text,
        embedding_to_pgvector,
        get_connection,
    ):
        profile_id = uuid.uuid4()
        embed_text.return_value = [0.1, 0.2]
        embedding_to_pgvector.return_value = "[0.1,0.2]"

        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchall.return_value = []
        get_connection.return_value = connection

        result = retrieve_chunks("account-specific question", profile_id)

        self.assertEqual(result, [])
        sql, parameters = cursor.execute.call_args.args
        normalized_sql = " ".join(sql.split())
        self.assertIn("and ga.profile_id = %s", normalized_sql)
        self.assertEqual(
            parameters,
            (
                "[0.1,0.2]",
                EMBEDDING_MODEL,
                profile_id,
                "[0.1,0.2]",
                20,
            ),
        )

    @patch("app.rag.generate_answer")
    @patch("app.rag.rerank_candidates")
    @patch("app.rag.retrieve_chunks")
    def test_rag_forwards_profile_to_retrieval(
        self,
        retrieve,
        rerank,
        generate,
    ):
        profile_id = uuid.uuid4()
        retrieve.return_value = []
        rerank.return_value = []
        generate.return_value = "No account-specific sources were found."

        response = answer_question("private question", profile_id)

        retrieve.assert_called_once_with("private question", profile_id)
        rerank.assert_called_once_with("private question", [])
        generate.assert_called_once_with("private question", [])
        self.assertEqual(response.sources, [])


if __name__ == "__main__":
    unittest.main()
