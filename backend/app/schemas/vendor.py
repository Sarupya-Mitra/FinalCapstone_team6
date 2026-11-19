from pydantic import BaseModel, Field, ConfigDict


# Schema for creating a vendor
class VendorCreate(BaseModel):

    v_name: str = Field(min_length=1, max_length=100)
    contact_ref: str = Field(min_length=1, max_length=150)
    active: bool = True


# Schema for updating a vendor
class VendorUpdate(BaseModel):

    v_name: str = Field(min_length=1, max_length=100)
    contact_ref: str = Field(min_length=1, max_length=150)
    active: bool


# Schema for returning vendor details
class VendorResponse(BaseModel):

    v_id: int
    v_name: str
    contact_ref: str
    active: bool

    model_config = ConfigDict(from_attributes=True)