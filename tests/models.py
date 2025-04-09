from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class MockRelatedModel(SQLModel, table=True):
    # __table_args__ = {"extend_existing": True}
    __tablename__ = "mockrelatedmodel"

    id: Optional[int] = Field(default=None, primary_key=True)
    related_name: str = Field(index=True)
    mock_models: list["MockModel"] = Relationship(
        back_populates="related_field",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )


class MockModel(SQLModel, table=True):
    # __table_args__ = {"extend_existing": True}
    __tablename__ = "mockmodel"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    value: Optional[int] = None
    related_field_id: Optional[int] = Field(
        default=None, foreign_key="mockrelatedmodel.id", index=True
    )
    related_field: Optional["MockRelatedModel"] = Relationship(
        back_populates="mock_models"
    )
