# app/core/vector_db.py

"""
Vector database module
Handles vector storage and similarity search using Pinecone, Qdrant, or ChromaDB
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from datetime import datetime
import hashlib
import json

from ..config import settings

logger = logging.getLogger(__name__)


class VectorDBBackend:
    """
    Base class for vector database backends
    """

    def create_index(self, index_name: str, dimension: int, metric: str = "cosine") -> bool:
        """
        Create a new index

        Args:
            index_name: Name of the index
            dimension: Vector dimension
            metric: Distance metric (cosine, euclidean, dot_product)

        Returns:
            True if successful
        """
        raise NotImplementedError

    def delete_index(self, index_name: str) -> bool:
        """
        Delete an index

        Args:
            index_name: Name of the index

        Returns:
            True if successful
        """
        raise NotImplementedError

    def upsert(
            self,
            index_name: str,
            vectors: List[List[float]],
            ids: List[str],
            metadata: List[dict] = None
    ) -> bool:
        """
        Insert or update vectors

        Args:
            index_name: Name of the index
            vectors: List of vectors
            ids: List of vector IDs
            metadata: Optional list of metadata dictionaries

        Returns:
            True if successful
        """
        raise NotImplementedError

    def query(
            self,
            index_name: str,
            query_vector: List[float],
            top_k: int = 10,
            filter_dict: dict = None
    ) -> List[Dict[str, Any]]:
        """
        Query for similar vectors

        Args:
            index_name: Name of the index
            query_vector: Query vector
            top_k: Number of results to return
            filter_dict: Optional metadata filter

        Returns:
            List of results with id, score, and metadata
        """
        raise NotImplementedError

    def delete(self, index_name: str, ids: List[str]) -> bool:
        """
        Delete vectors by ID

        Args:
            index_name: Name of the index
            ids: List of vector IDs to delete

        Returns:
            True if successful
        """
        raise NotImplementedError

    def fetch(self, index_name: str, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch vectors by ID

        Args:
            index_name: Name of the index
            ids: List of vector IDs to fetch

        Returns:
            List of vectors with metadata
        """
        raise NotImplementedError

    def get_stats(self, index_name: str) -> dict:
        """
        Get index statistics

        Args:
            index_name: Name of the index

        Returns:
            Statistics dictionary
        """
        raise NotImplementedError


class PineconeBackend(VectorDBBackend):
    """
    Pinecone vector database backend
    """

    def __init__(self, api_key: str, environment: str):
        """
        Initialize Pinecone backend

        Args:
            api_key: Pinecone API key
            environment: Pinecone environment
        """
        try:
            import pinecone

            pinecone.init(api_key=api_key, environment=environment)
            self.pinecone = pinecone

            logger.info("Pinecone backend initialized")

        except ImportError:
            raise ImportError(
                "pinecone-client is required for Pinecone backend. "
                "Install with: pip install pinecone-client"
            )
        except Exception as e:
            logger.error(f"Error initializing Pinecone: {str(e)}")
            raise

    def create_index(self, index_name: str, dimension: int, metric: str = "cosine") -> bool:
        """Create Pinecone index"""
        try:
            if index_name not in self.pinecone.list_indexes():
                self.pinecone.create_index(
                    name=index_name,
                    dimension=dimension,
                    metric=metric
                )
                logger.info(f"Created Pinecone index: {index_name}")
            return True
        except Exception as e:
            logger.error(f"Error creating Pinecone index: {str(e)}")
            return False

    def delete_index(self, index_name: str) -> bool:
        """Delete Pinecone index"""
        try:
            if index_name in self.pinecone.list_indexes():
                self.pinecone.delete_index(index_name)
                logger.info(f"Deleted Pinecone index: {index_name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting Pinecone index: {str(e)}")
            return False

    def upsert(
            self,
            index_name: str,
            vectors: List[List[float]],
            ids: List[str],
            metadata: List[dict] = None
    ) -> bool:
        """Upsert vectors to Pinecone"""
        try:
            index = self.pinecone.Index(index_name)

            # Prepare vectors for upsert
            vectors_to_upsert = []
            for i, (vec_id, vector) in enumerate(zip(ids, vectors)):
                item = (vec_id, vector)
                if metadata and i < len(metadata):
                    item = (vec_id, vector, metadata[i])
                vectors_to_upsert.append(item)

            # Upsert in batches
            batch_size = 100
            for i in range(0, len(vectors_to_upsert), batch_size):
                batch = vectors_to_upsert[i:i + batch_size]
                index.upsert(vectors=batch)

            logger.info(f"Upserted {len(vectors)} vectors to Pinecone index: {index_name}")
            return True

        except Exception as e:
            logger.error(f"Error upserting to Pinecone: {str(e)}")
            return False

    def query(
            self,
            index_name: str,
            query_vector: List[float],
            top_k: int = 10,
            filter_dict: dict = None
    ) -> List[Dict[str, Any]]:
        """Query Pinecone index"""
        try:
            index = self.pinecone.Index(index_name)

            query_params = {
                "vector": query_vector,
                "top_k": top_k,
                "include_metadata": True
            }

            if filter_dict:
                query_params["filter"] = filter_dict

            results = index.query(**query_params)

            # Format results
            formatted_results = []
            for match in results.matches:
                formatted_results.append({
                    "id": match.id,
                    "score": match.score,
                    "metadata": match.meta_data
                })

            return formatted_results

        except Exception as e:
            logger.error(f"Error querying Pinecone: {str(e)}")
            return []

    def delete(self, index_name: str, ids: List[str]) -> bool:
        """Delete vectors from Pinecone"""
        try:
            index = self.pinecone.Index(index_name)
            index.delete(ids=ids)
            logger.info(f"Deleted {len(ids)} vectors from Pinecone index: {index_name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting from Pinecone: {str(e)}")
            return False

    def fetch(self, index_name: str, ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch vectors from Pinecone"""
        try:
            index = self.pinecone.Index(index_name)
            results = index.fetch(ids=ids)

            formatted_results = []
            for vec_id, data in results.vectors.items():
                formatted_results.append({
                    "id": vec_id,
                    "values": data.values,
                    "metadata": data.meta_data
                })

            return formatted_results

        except Exception as e:
            logger.error(f"Error fetching from Pinecone: {str(e)}")
            return []

    def get_stats(self, index_name: str) -> dict:
        """Get Pinecone index statistics"""
        try:
            index = self.pinecone.Index(index_name)
            stats = index.describe_index_stats()

            return {
                "total_vector_count": stats.total_vector_count,
                "dimension": stats.dimension,
                "index_fullness": stats.index_fullness
            }

        except Exception as e:
            logger.error(f"Error getting Pinecone stats: {str(e)}")
            return {}


class QdrantBackend(VectorDBBackend):
    """
    Qdrant vector database backend
    """

    def __init__(self, url: str = settings.QDRANT_URL, api_key: str = None):
        """
        Initialize Qdrant backend

        Args:
            url: Qdrant server URL
            api_key: Optional API key
        """
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self.client = QdrantClient(url=url, api_key=api_key)
            self.Distance = Distance
            self.VectorParams = VectorParams

            logger.info("Qdrant backend initialized")

        except ImportError:
            raise ImportError(
                "qdrant-client is required for Qdrant backend. "
                "Install with: pip install qdrant-client"
            )
        except Exception as e:
            logger.error(f"Error initializing Qdrant: {str(e)}")
            raise

    def create_index(self, index_name: str, dimension: int, metric: str = "cosine") -> bool:
        """Create Qdrant collection"""
        try:
            from qdrant_client.models import Distance, VectorParams

            # Map metric to Qdrant distance
            distance_map = {
                "cosine": Distance.COSINE,
                "euclidean": Distance.EUCLID,
                "dot_product": Distance.DOT
            }

            distance = distance_map.get(metric, Distance.COSINE)

            self.client.create_collection(
                collection_name=index_name,
                vectors_config=VectorParams(size=dimension, distance=distance)
            )

            logger.info(f"Created Qdrant collection: {index_name}")
            return True

        except Exception as e:
            logger.error(f"Error creating Qdrant collection: {str(e)}")
            return False

    def delete_index(self, index_name: str) -> bool:
        """Delete Qdrant collection"""
        try:
            self.client.delete_collection(collection_name=index_name)
            logger.info(f"Deleted Qdrant collection: {index_name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting Qdrant collection: {str(e)}")
            return False

    def upsert(
            self,
            index_name: str,
            vectors: List[List[float]],
            ids: List[str],
            metadata: List[dict] = None
    ) -> bool:
        """Upsert vectors to Qdrant"""
        try:
            from qdrant_client.models import PointStruct

            points = []
            for i, (vec_id, vector) in enumerate(zip(ids, vectors)):
                payload = metadata[i] if metadata and i < len(metadata) else {}
                points.append(
                    PointStruct(
                        id=vec_id,
                        vector=vector,
                        payload=payload
                    )
                )

            self.client.upsert(
                collection_name=index_name,
                points=points
            )

            logger.info(f"Upserted {len(vectors)} vectors to Qdrant collection: {index_name}")
            return True

        except Exception as e:
            logger.error(f"Error upserting to Qdrant: {str(e)}")
            return False

    def query(
            self,
            index_name: str,
            query_vector: List[float],
            top_k: int = 10,
            filter_dict: dict = None
    ) -> List[Dict[str, Any]]:
        """Query Qdrant collection"""
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            search_params = {
                "collection_name": index_name,
                "query_vector": query_vector,
                "limit": top_k
            }

            # Add filter if provided
            if filter_dict:
                conditions = []
                for key, value in filter_dict.items():
                    conditions.append(
                        FieldCondition(key=key, match=MatchValue(value=value))
                    )
                search_params["query_filter"] = Filter(must=conditions)

            results = self.client.search(**search_params)

            # Format results
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "id": result.id,
                    "score": result.score,
                    "metadata": result.payload
                })

            return formatted_results

        except Exception as e:
            logger.error(f"Error querying Qdrant: {str(e)}")
            return []

    def delete(self, index_name: str, ids: List[str]) -> bool:
        """Delete vectors from Qdrant"""
        try:
            from qdrant_client.models import PointIdsList

            self.client.delete(
                collection_name=index_name,
                points_selector=PointIdsList(points=ids)
            )

            logger.info(f"Deleted {len(ids)} vectors from Qdrant collection: {index_name}")
            return True

        except Exception as e:
            logger.error(f"Error deleting from Qdrant: {str(e)}")
            return False

    def fetch(self, index_name: str, ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch vectors from Qdrant"""
        try:
            results = self.client.retrieve(
                collection_name=index_name,
                ids=ids,
                with_vectors=True
            )

            formatted_results = []
            for result in results:
                formatted_results.append({
                    "id": result.id,
                    "values": result.vector,
                    "metadata": result.payload
                })

            return formatted_results

        except Exception as e:
            logger.error(f"Error fetching from Qdrant: {str(e)}")
            return []

    def get_stats(self, index_name: str) -> dict:
        """Get Qdrant collection statistics"""
        try:
            info = self.client.get_collection(collection_name=index_name)

            return {
                "total_vector_count": info.points_count,
                "dimension": info.config.params.vectors.size,
                "status": info.status
            }

        except Exception as e:
            logger.error(f"Error getting Qdrant stats: {str(e)}")
            return {}


class ChromaDBBackend(VectorDBBackend):
    """
    ChromaDB vector database backend
    """

    def __init__(self, persist_directory: str = None):
        """
        Initialize ChromaDB backend

        Args:
            persist_directory: Directory for persistent storage
        """
        try:
            import chromadb
            from chromadb.config import Settings

            if persist_directory:
                self.client = chromadb.Client(Settings(
                    persist_directory=persist_directory,
                    anonymized_telemetry=False
                ))
            else:
                self.client = chromadb.Client()

            logger.info("ChromaDB backend initialized")

        except ImportError:
            raise ImportError(
                "chromadb is required for ChromaDB backend. "
                "Install with: pip install chromadb"
            )
        except Exception as e:
            logger.error(f"Error initializing ChromaDB: {str(e)}")
            raise

    def create_index(self, index_name: str, dimension: int, metric: str = "cosine") -> bool:
        """Create ChromaDB collection"""
        try:
            # Map metric to ChromaDB distance
            distance_map = {
                "cosine": "cosine",
                "euclidean": "l2",
                "dot_product": "ip"
            }

            distance = distance_map.get(metric, "cosine")

            self.client.create_collection(
                name=index_name,
                metadata={"hnsw:space": distance}
            )

            logger.info(f"Created ChromaDB collection: {index_name}")
            return True

        except Exception as e:
            logger.error(f"Error creating ChromaDB collection: {str(e)}")
            return False

    def delete_index(self, index_name: str) -> bool:
        """Delete ChromaDB collection"""
        try:
            self.client.delete_collection(name=index_name)
            logger.info(f"Deleted ChromaDB collection: {index_name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting ChromaDB collection: {str(e)}")
            return False

    def upsert(
            self,
            index_name: str,
            vectors: List[List[float]],
            ids: List[str],
            metadata: List[dict] = None
    ) -> bool:
        """Upsert vectors to ChromaDB"""
        try:
            collection = self.client.get_collection(name=index_name)

            collection.upsert(
                embeddings=vectors,
                ids=ids,
                metadatas=metadata
            )

            logger.info(f"Upserted {len(vectors)} vectors to ChromaDB collection: {index_name}")
            return True

        except Exception as e:
            logger.error(f"Error upserting to ChromaDB: {str(e)}")
            return False

    def query(
            self,
            index_name: str,
            query_vector: List[float],
            top_k: int = 10,
            filter_dict: dict = None
    ) -> List[Dict[str, Any]]:
        """Query ChromaDB collection"""
        try:
            collection = self.client.get_collection(name=index_name)

            query_params = {
                "query_embeddings": [query_vector],
                "n_results": top_k
            }

            if filter_dict:
                query_params["where"] = filter_dict

            results = collection.query(**query_params)

            # Format results
            formatted_results = []
            if results['ids'] and len(results['ids']) > 0:
                for i, vec_id in enumerate(results['ids'][0]):
                    formatted_results.append({
                        "id": vec_id,
                        "score": 1 - results['distances'][0][i],  # Convert distance to similarity
                        "metadata": results['metadatas'][0][i] if results['metadatas'] else {}
                    })

            return formatted_results

        except Exception as e:
            logger.error(f"Error querying ChromaDB: {str(e)}")
            return []

    def delete(self, index_name: str, ids: List[str]) -> bool:
        """Delete vectors from ChromaDB"""
        try:
            collection = self.client.get_collection(name=index_name)
            collection.delete(ids=ids)

            logger.info(f"Deleted {len(ids)} vectors from ChromaDB collection: {index_name}")
            return True

        except Exception as e:
            logger.error(f"Error deleting from ChromaDB: {str(e)}")
            return False

    def fetch(self, index_name: str, ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch vectors from ChromaDB"""
        try:
            collection = self.client.get_collection(name=index_name)
            results = collection.get(ids=ids, include=["embeddings", "metadatas"])

            formatted_results = []
            for i, vec_id in enumerate(results['ids']):
                formatted_results.append({
                    "id": vec_id,
                    "values": results['embeddings'][i] if results['embeddings'] else [],
                    "metadata": results['metadatas'][i] if results['metadatas'] else {}
                })

            return formatted_results

        except Exception as e:
            logger.error(f"Error fetching from ChromaDB: {str(e)}")
            return []

    def get_stats(self, index_name: str) -> dict:
        """Get ChromaDB collection statistics"""
        try:
            collection = self.client.get_collection(name=index_name)
            count = collection.count()

            return {
                "total_vector_count": count,
                "name": index_name
            }

        except Exception as e:
            logger.error(f"Error getting ChromaDB stats: {str(e)}")
            return {}


class VectorDBManager:
    """
    Vector database manager
    """

    def __init__(self, backend: VectorDBBackend = None):
        """
        Initialize vector database manager

        Args:
            backend: Vector database backend to use
        """
        if backend:
            self.backend = backend
        else:
            # Initialize default backend based on settings
            self.backend = self._initialize_default_backend()

        logger.info(f"Vector DB manager initialized with {type(self.backend).__name__}")

    def _initialize_default_backend(self) -> VectorDBBackend:
        """Initialize default backend from settings"""
        # vector_db_type = getattr(settings, 'VECTOR_DB_TYPE', 'chromadb')
        ## Hooman:
        # change default vector db to qdrant
        vector_db_type = getattr(settings, 'VECTOR_DB_TYPE', 'qdrant')

        if vector_db_type == 'pinecone':
            api_key = getattr(settings, 'PINECONE_API_KEY', '')
            environment = getattr(settings, 'PINECONE_ENVIRONMENT', '')
            return PineconeBackend(api_key=api_key, environment=environment)

        elif vector_db_type == 'qdrant':
            url = getattr(settings, 'QDRANT_URL', 'http://localhost:6333')
            api_key = getattr(settings, 'QDRANT_API_KEY', None)
            return QdrantBackend(url=url, api_key=api_key)

        else:  # Default to ChromaDB
            persist_dir = getattr(settings, 'CHROMADB_PERSIST_DIR', './chromadb')
            return ChromaDBBackend(persist_directory=persist_dir)

    def add_documents(
            self,
            index_name: str,
            texts: List[str],
            embeddings: List[List[float]],
            metadata: List[dict] = None
    ) -> bool:
        """
        Add documents to vector database

        Args:
            index_name: Name of the index
            texts: List of text documents
            embeddings: List of embeddings
            metadata: Optional list of metadata

        Returns:
            True if successful
        """
        # Generate IDs from text hashes
        ids = [hashlib.md5(text.encode()).hexdigest() for text in texts]

        # Add text to metadata
        if metadata is None:
            metadata = []

        for i, text in enumerate(texts):
            if i >= len(metadata):
                metadata.append({})
            metadata[i]['text'] = text
            metadata[i]['indexed_at'] = datetime.utcnow().isoformat()

        return self.backend.upsert(index_name, embeddings, ids, metadata)

    def search(
            self,
            index_name: str,
            query_embedding: List[float],
            top_k: int = 5,
            filter_dict: dict = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents

        Args:
            index_name: Name of the index
            query_embedding: Query embedding
            top_k: Number of results
            filter_dict: Optional metadata filter

        Returns:
            List of search results
        """
        return self.backend.query(index_name, query_embedding, top_k, filter_dict)

    def delete_documents(self, index_name: str, document_ids: List[str]) -> bool:
        """
        Delete documents from index

        Args:
            index_name: Name of the index
            document_ids: List of document IDs

        Returns:
            True if successful
        """
        return self.backend.delete(index_name, document_ids)

    def get_index_stats(self, index_name: str) -> dict:
        """
        Get index statistics

        Args:
            index_name: Name of the index

        Returns:
            Statistics dictionary
        """
        return self.backend.get_stats(index_name)


# Global vector database manager instance
vector_db_manager = VectorDBManager()


def get_vector_db() -> VectorDBManager:
    """
    Get vector database manager instance

    Returns:
        VectorDBManager instance
    """
    return vector_db_manager