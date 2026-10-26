from pydantic import BaseModel, Field
from typing import List

class TelemetryPacket(BaseModel):
    node_id: str = Field(..., example="TRUCK-01")
    seq_num: int = Field(..., ge=0, description="Αύξων αριθμός πακέτου")
    timestamp: float = Field(..., description="Unix timestamp τη στιγμή της μέτρησης")
    temp_c: float = Field(..., description="Θερμοκρασία σε βαθμούς Κελσίου")
    voltage_v: float = Field(..., description="Τάση μπαταρίας/τροφοδοσίας σε Volt")
    lat: float = Field(..., description="Γεωγραφικό πλάτος (GPS)")
    lon: float = Field(..., description="Γεωγραφικό μήκος (GPS)")
    buffered: bool = Field(default=False, description="True αν προήλθε από το Offline Ring Buffer")

class TelemetryBatch(BaseModel):
    packets: List[TelemetryPacket]