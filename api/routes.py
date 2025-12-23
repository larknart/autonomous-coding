"""
FastAPI Routes
==============

REST API endpoints for feature management.
"""

from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.database import Feature, get_db


# Pydantic models for request/response validation

class FeatureCreate(BaseModel):
    """Schema for creating a feature."""
    category: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    steps: List[str] = Field(..., min_items=1)


class FeatureBulkCreate(BaseModel):
    """Schema for bulk creating features."""
    features: List[FeatureCreate] = Field(..., min_items=1)


class FeatureUpdate(BaseModel):
    """Schema for updating a feature (only passes field allowed)."""
    passes: bool


class FeatureResponse(BaseModel):
    """Schema for feature response."""
    id: int
    priority: int
    category: str
    name: str
    description: str
    steps: List[str]
    passes: bool

    class Config:
        from_attributes = True


class FeatureListResponse(BaseModel):
    """Schema for paginated feature list response."""
    features: List[FeatureResponse]
    total: int
    limit: int
    offset: int


class StatsResponse(BaseModel):
    """Schema for statistics response."""
    passing: int
    total: int
    percentage: float


class BulkCreateResponse(BaseModel):
    """Schema for bulk create response."""
    created: int


class HealthResponse(BaseModel):
    """Schema for health check response."""
    status: str
    database: str


def create_app(project_dir: Path) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        project_dir: Directory containing the project

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Feature API",
        description="API for managing features in the autonomous coding system",
        version="1.0.0",
    )

    @app.get("/health", response_model=HealthResponse)
    def health_check(db: Session = Depends(get_db)):
        """Health check endpoint."""
        try:
            # Try a simple query to verify database connectivity
            db.query(Feature).first()
            return {"status": "healthy", "database": "connected"}
        except Exception as e:
            return {"status": "unhealthy", "database": str(e)}

    @app.get("/features", response_model=FeatureListResponse)
    def list_features(
        limit: int = Query(50, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        passes: Optional[bool] = Query(None),
        category: Optional[str] = Query(None),
        db: Session = Depends(get_db),
    ):
        """
        List features with pagination and optional filtering.

        - **limit**: Maximum number of features to return (1-1000)
        - **offset**: Number of features to skip
        - **passes**: Filter by pass status (true/false)
        - **category**: Filter by category name
        """
        query = db.query(Feature)

        # Apply filters
        if passes is not None:
            query = query.filter(Feature.passes == passes)
        if category is not None:
            query = query.filter(Feature.category == category)

        # Get total count before pagination
        total = query.count()

        # Apply ordering and pagination
        features = (
            query.order_by(Feature.priority.asc(), Feature.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "features": [f.to_dict() for f in features],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/features/next", response_model=FeatureResponse)
    def get_next_feature(db: Session = Depends(get_db)):
        """
        Get the highest-priority pending feature.

        Returns the feature with the lowest priority number that has passes=false.
        Returns 404 if all features are passing.
        """
        feature = (
            db.query(Feature)
            .filter(Feature.passes == False)
            .order_by(Feature.priority.asc(), Feature.id.asc())
            .first()
        )

        if feature is None:
            raise HTTPException(
                status_code=404,
                detail="All features are passing! No more work to do.",
            )

        return feature.to_dict()

    @app.get("/features/stats", response_model=StatsResponse)
    def get_stats(db: Session = Depends(get_db)):
        """Get statistics about feature completion."""
        total = db.query(Feature).count()
        passing = db.query(Feature).filter(Feature.passes == True).count()
        percentage = round((passing / total) * 100, 1) if total > 0 else 0.0

        return {
            "passing": passing,
            "total": total,
            "percentage": percentage,
        }

    @app.get("/features/{feature_id}", response_model=FeatureResponse)
    def get_feature(feature_id: int, db: Session = Depends(get_db)):
        """Get a specific feature by ID."""
        feature = db.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail="Feature not found")

        return feature.to_dict()

    @app.post("/features", response_model=FeatureResponse, status_code=201)
    def create_feature(feature: FeatureCreate, db: Session = Depends(get_db)):
        """Create a single feature."""
        # Get the next priority (max + 1)
        max_priority = db.query(Feature.priority).order_by(Feature.priority.desc()).first()
        next_priority = (max_priority[0] + 1) if max_priority else 1

        db_feature = Feature(
            priority=next_priority,
            category=feature.category,
            name=feature.name,
            description=feature.description,
            steps=feature.steps,
            passes=False,
        )

        db.add(db_feature)
        db.commit()
        db.refresh(db_feature)

        return db_feature.to_dict()

    @app.post("/features/bulk", response_model=BulkCreateResponse, status_code=201)
    def create_features_bulk(data: FeatureBulkCreate, db: Session = Depends(get_db)):
        """
        Create multiple features in a single request.

        Features are assigned IDs and priorities based on their order in the array.
        All features start with passes=false.
        """
        # Get the starting priority
        max_priority = db.query(Feature.priority).order_by(Feature.priority.desc()).first()
        start_priority = (max_priority[0] + 1) if max_priority else 1

        created_count = 0
        for i, feature in enumerate(data.features):
            db_feature = Feature(
                priority=start_priority + i,
                category=feature.category,
                name=feature.name,
                description=feature.description,
                steps=feature.steps,
                passes=False,
            )
            db.add(db_feature)
            created_count += 1

        db.commit()

        return {"created": created_count}

    @app.patch("/features/{feature_id}", response_model=FeatureResponse)
    def update_feature(
        feature_id: int, update: FeatureUpdate, db: Session = Depends(get_db)
    ):
        """
        Update a feature's pass status.

        Only the 'passes' field can be modified.
        """
        feature = db.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail="Feature not found")

        feature.passes = update.passes
        db.commit()
        db.refresh(feature)

        return feature.to_dict()

    @app.delete("/features/{feature_id}", status_code=204)
    def delete_feature(feature_id: int, db: Session = Depends(get_db)):
        """Delete a feature (use with caution)."""
        feature = db.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail="Feature not found")

        db.delete(feature)
        db.commit()

        return None

    return app
