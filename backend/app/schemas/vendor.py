from pydantic import BaseModel, Field, ConfigDict,model_validator
from datetime import datetime


# Schema for creating a vendor
class VendorCreate(BaseModel):

    vendor_name: str = Field(min_length=1, max_length=100)
    contact_reference: str = Field(min_length=1, max_length=150)
    tax_id: str = Field(min_length=1, max_length=50)
    active: bool = True


# Schema for updating a vendor
class VendorUpdate(BaseModel):

    vendor_name: str | None = Field(default=None,min_length=1, max_length=100)
    contact_reference: str|None = Field(default=None,min_length=1, max_length=150)
    tax_id: str | None = Field(default=None, max_length=50)
    active: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_null_values(cls, data):
        if isinstance(data, dict):
            null_fields = [
                field for field, value in data.items()
                if value is None
            ]

            if null_fields:
                raise ValueError(
                    f"These fields cannot be null: {', '.join(null_fields)}"
                )

        return data


# Schema for returning vendor details
class VendorResponse(BaseModel):

    vendor_id: int
    vendor_name: str
    contact_reference: str
    tax_id: str
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

VendorResponse.model_rebuild()