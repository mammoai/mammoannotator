import os
from dataclasses import dataclass
from typing import List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pydicom
from mammoannotator.mri import list_files
from PIL import Image
from pydicom import dcmread


@dataclass
class DicomSlice:
    image: np.array
    tags: dict

    @classmethod
    def from_path(cls, dcm_path: str) -> Tuple[np.array, dict]:
        ds = dcmread(dcm_path)
        tags = cls.read_relevant_tags(ds)
        image = ds.pixel_array
        #image = cls.window_image_from_tags(image, tags)
        return cls(image=image, tags=tags)

    @staticmethod
    def read_relevant_tags(ds: pydicom.Dataset):
        pixel_spacing_row, pixel_spacing_column = [float(d) for d in ds.PixelSpacing]
        dcm_dict = dict(
            # path = dcm_path,
            request_procedure_id=ds.RequestedProcedureID,
            # Series properties
            acquisition_time=float(ds.AcquisitionTime),
            content_time=float(ds.ContentTime),
            trigger_time=float(ds.TriggerTime),
            series_number=int(ds.SeriesNumber),
            temporal_position_identifier=int(ds.TemporalPositionIdentifier),
            # Slice properties
            instance_creation_time=float(ds.InstanceCreationTime),
            instance_number=int(ds.InstanceNumber),
            slice_location=float(ds.SliceLocation),  # in mm (signed)
            slice_thickness=float(ds.SliceThickness),
            # Image properties
            rows=int(ds.Rows),
            columns=int(ds.Columns),
            pixel_spacing_row=pixel_spacing_row,  # in mm
            pixel_spacing_column=pixel_spacing_column,  # in mm
            window_center=float(ds.WindowCenter),
            window_width=float(ds.WindowWidth),
            rescale_intercept=float(ds.RescaleIntercept),
            rescale_slope=float(ds.RescaleSlope),
            # SpacingBetweenSlices
        )
        return dcm_dict

    @staticmethod
    def window_image(
    im: np.array,
    window_center: float,
    window_width: float,
    rescale_intercept: float,
    rescale_slope: float,
    dtype=np.uint8,
    **kwargs  # kwargs is just to allow the easy use of the **tags magic
    ):
        im = im * rescale_slope + rescale_intercept
        im_min = max(window_center - window_width // 2, 0)
        im_max = min(window_center + window_width // 2, 0xFFFF)
        im[im < im_min] = im_min
        im[im > im_max] = im_max
        return im.astype(dtype)

    @staticmethod
    def window_image_from_tags(im: np.array, tags: dict):
        return DicomSlice.window_image(im, **tags)

@dataclass
class DicomSeries:
    volume: np.array
    slices: List[DicomSlice]
    tags: dict 

    # the following tags should be equal to all Slices in the series
    # so aggregate them into the Series, else break.
    tag_names = [
        "request_procedure_id",
        "acquisition_time",
        "content_time",
        "trigger_time",
        "series_number",
        "temporal_position_identifier",
        "slice_thickness",
        "rows",
        "columns",
        "pixel_spacing_row",
        "pixel_spacing_column",
    ]

    @classmethod
    def from_path(cls, series_path: str):
        slices_files = list_files(series_path, ".dcm")
        slices = []
        for fp in slices_files:
            dcm_slice = DicomSlice.from_path(fp)
            slices.append(dcm_slice)
        slices = cls.sort_slices(slices)
        volume = np.stack([s.image for s in slices])
        tags = cls.collapse_tags(slices, cls.tag_names, assert_unique=True)
        return cls(volume=volume, slices=slices, tags=tags)

    @staticmethod
    def collapse_tag(slices:List[DicomSlice], tag_name:str, assert_unique):
        v = slices[0].tags[tag_name]
        if assert_unique:
            all_vals = np.array([s.tags[tag_name] for s in slices[1:]])
            assert all(v == all_vals), f'Could not collapse tag {tag_name}: {all_vals}'
        return v
    
    @staticmethod
    def collapse_tags(slices:List[DicomSlice], tag_names:List[str], assert_unique=True):
        dcm_tags = dict()
        for tag in tag_names:
            dcm_tags[tag] = DicomSeries.collapse_tag(slices, tag, assert_unique)
        return dcm_tags


    @staticmethod
    def sort_slices(slices: List[DicomSlice], sorting_tag:str = 'slice_location'):
        return sorted(slices, key=lambda s: s.tags[sorting_tag])

    def get_tag_array(self, tag_name: str):
        return np.array([s.tags[tag_name] for s in self.slices])

    def get_spacing(self):
        '''returns the spacing between slices, between rows and between columns'''
        return self.tags['slice_thickness'], self.tags["pixel_spacing_row"], self.tags["pixel_spacing_column"]



if __name__ == "__main__":
    study_path = "/Users/annotator/Desktop/MR scans/6a595236754e76732f766a2f394463337373366467673d3d/Fo3Qxe1aNysvwql1vNG8FSiFSLASHRf5aQjcpXAPWEQvQ6E+Ob0I83Y0p4vXl+nYtRDiK"
    volume_folder = "401002_eTHRIVE_Tra 1-6 dyn"
    series_path = os.path.join(study_path, volume_folder)
    slices_files = list_files(series_path, ".dcm")
    dcm_series = DicomSeries.from_path(series_path)
    # print(dcm_series.tags)
    from PIL import Image
    mip = dcm_series.volume.max(axis=0)
    mip = DicomSlice.window_image(mip, window_center=1000, window_width=2000, rescale_intercept=0, rescale_slope=20)
    Image.fromarray(mip).show()