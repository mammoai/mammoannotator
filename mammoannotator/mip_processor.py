import os
from dataclasses import dataclass
from typing import List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pydicom
from mammoannotator.mri import list_files
from pydicom import dcmread
import cv2

from coma_db.mongo_dao import ImageMetadataDao

# temp just for debugging
window_center_val = 250
window_width_val = 500
show_time = 50

def parse_image_orientation(im_or):
    """For reference, see: https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.7.6.2.html#sect_C.7.6.2.1.1"""
    values = [float(i) for i in im_or]
    row_x, row_y, row_z, col_x, col_y, col_z = values
    return row_x, row_y, row_z, col_x, col_y, col_z

@dataclass
class DicomSlice:
    image: np.array
    tags: dict
    path: str

    @staticmethod
    def correct_orientation(im:np.array, tags:dict):
        if round(tags['image_orientation_row']) < 0:
            im = np.flip(im, axis=-1)
            tags['image_orientation_row'] = 1
        if round(tags['image_orientation_col']) < 0:
            im = np.flip(im, axis=-2)
            tags['image_orientation_col'] = 1
        return im, tags


    @classmethod
    def from_path(cls, dcm_path: str, to_uint8=True) -> Tuple[np.array, dict]:
        ds = dcmread(dcm_path)
        tags = cls.read_relevant_tags(ds)
        image = ds.pixel_array
        image, tags = cls.correct_orientation(image, tags)
        path = dcm_path
        return cls(image=image, tags=tags, path=path)

    @staticmethod
    def read_relevant_tags(ds: pydicom.Dataset):
        pixel_spacing_row, pixel_spacing_column = [float(d) for d in ds.PixelSpacing]
        row_dir, _, _, _, col_dir, _ = parse_image_orientation(ds.ImageOrientationPatient)
        dcm_dict = dict(
            # General Study
            # request_procedure_id=ds.RequestedProcedureID, # also check inside RequestAttributesSequence
            study_date=ds.StudyDate,
            study_time=ds.StudyTime,
            # Series properties
            series_description=ds.SeriesDescription,
            acquisition_time=float(ds.AcquisitionTime),
            content_time=float(ds.ContentTime),
            # trigger_time=float(ds.TriggerTime),
            series_number=int(ds.SeriesNumber),
            # temporal_position_identifier=int(ds.TemporalPositionIdentifier),
            # Slice properties
            # instance_creation_time=float(ds.InstanceCreationTime),
            instance_number=int(ds.InstanceNumber),
            slice_location=float(ds.SliceLocation),  # in mm (signed)
            slice_thickness=float(ds.SliceThickness),  # in mm
            # Image properties
            rows=int(ds.Rows),
            columns=int(ds.Columns),
            pixel_spacing_row=pixel_spacing_row,  # in mm
            pixel_spacing_column=pixel_spacing_column,  # in mm
            window_center=float(ds.WindowCenter),
            window_width=float(ds.WindowWidth),
            image_orientation_row = row_dir,
            image_orientation_col = col_dir
            # rescale_intercept=float(ds.RescaleIntercept),
            # rescale_slope=float(ds.RescaleSlope),
            # SpacingBetweenSlices
        )
        return dcm_dict

    @staticmethod
    def window_image(
        im: np.array, window_center: float, window_width: float, **kwargs
    ) -> np.array:
        """
        Window an image according to the window center and width
        """
        im = im.astype(np.float32)
        im_min = window_center - window_width / 2
        im_max = window_center + window_width / 2
        im = np.clip(im, im_min, im_max)
        max = im.max()
        min = im.min()
        im = (im - im_min) / window_width
        max = im.max()
        min = im.min()
        im = np.clip(im*255, 0, 255).astype(np.uint8)
        return im
        

    def show(self, title=None):
        position = self.tags["slice_location"]
        title = (
            f"{os.path.split(self.path)[0].split('/')[-1]} at {position} mm"
            if title is None
            else title
        )
        image = self.window_image(self.image, window_center_val, window_width_val)
        cv2.imshow(title, image)
        cv2.waitKey(show_time)


@dataclass
class DicomSeries:
    volume: np.array # dims are [slice, column, row]
    slices: List[DicomSlice]
    tags: dict
    path: str

    # the following tags should be equal to all Slices in the series
    # so aggregate them into the Series, else break.
    tag_names = [
        # "request_procedure_id",
        "series_description",
        "acquisition_time",
        # "content_time", # did not work for ssub series
        # "trigger_time",
        "series_number",
        # "temporal_position_identifier",
        "slice_thickness",
        "rows",
        "columns",
        "pixel_spacing_row",
        "pixel_spacing_column",
        "image_orientation_row",
        "image_orientation_col"
    ]

    @classmethod
    def from_path(cls, series_path: str):
        slices_paths = list_files(series_path, ".dcm")
        return cls.from_slice_paths(slices_paths)
    
    @classmethod
    def from_slice_paths(cls, slice_paths:List[str]):
        series_path = os.path.split(slice_paths[0])[0]
        slices = []
        for fp in slice_paths:
            dcm_slice = DicomSlice.from_path(fp)
            slices.append(dcm_slice)
        slices = cls.sort_slices(slices)
        volume = np.stack([s.image for s in slices])
        tags = cls.collapse_tags(slices, cls.tag_names, assert_unique=True)
        return cls(volume=volume, slices=slices, tags=tags, path=series_path)

    @classmethod # TODO: this method should be replaced with a from coma_db.model.RadiologicalSeries instead of the individual ids of the slices
    def from_slice_ids(cls, slices_ids:List[str], dao:ImageMetadataDao):
        slice_paths = [dao.get_by_id(i, obj=False)["_filepath"] for i in slices_ids]
        return cls.from_slice_paths(slice_paths)

    @staticmethod
    def collapse_tag(slices: List[DicomSlice], tag_name: str, assert_unique):
        v = slices[0].tags[tag_name]
        if assert_unique:
            all_vals = np.array([s.tags[tag_name] for s in slices[1:]])
            assert all(v == all_vals), f"Could not collapse tag {tag_name}: {all_vals}"
        return v

    @staticmethod
    def collapse_tags(
        slices: List[DicomSlice], tag_names: List[str], assert_unique=True
    ):
        dcm_tags = dict()
        for tag in tag_names:
            dcm_tags[tag] = DicomSeries.collapse_tag(slices, tag, assert_unique)
        return dcm_tags

    @staticmethod
    def sort_slices(slices: List[DicomSlice], sorting_tag: str = "slice_location"):
        return sorted(slices, key=lambda s: s.tags[sorting_tag])

    def get_tag_array(self, tag_name: str):
        return np.array([s.tags[tag_name] for s in self.slices])

    def get_spacing(self):
        """returns the spacing between slices, between rows and between columns"""
        return (
            self.tags["slice_thickness"],
            self.tags["pixel_spacing_row"],
            self.tags["pixel_spacing_column"],
        )

    def get_volume_laterality(self, laterality: str, rm_chest=False):
        assert laterality in [
            "left",
            "right",
            "all",
        ], f'laterality must be one of {["left", "right", "all"]}, not {laterality}'
        z, y, x = self.volume.shape
        volume = self.volume
        if rm_chest:
            chest_start = self.find_chest_start()
            volume = volume[:chest_start, :, :]
        if laterality == "left":
            return volume[:, :, x // 2 :]
        if laterality == "right":
            return volume[:, :, 0 : x // 2]
        if laterality == "all":
            return volume

    def mip(self, laterality: str, view: str):
        """
        Returns a maximum intensity projection of the volume
        """
        volume = self.get_volume_laterality(laterality)
        assert view in [
            "axial",
            "coronal",
            "sagittal",
        ], f'view must be one of {["axial", "coronal", "sagittal"]}'
        if view == "sagittal":
            return np.max(volume, axis=0)
        elif view == "coronal":
            return np.max(volume, axis=1)
        elif view == "axial":
            return np.max(volume, axis=2)

    def __sub__(self, other):
        """Subtract the volumes, remove other info"""
        # TODO: find a good way to aggregate the tags
        assert (
            self.volume.shape == other.volume.shape
        ), f"{self.volume.shape} != {other.volume.shape}"
        volume = self.volume.astype(np.int32) - other.volume.astype(np.int32)
        path = os.path.split(self.path)[1] + "_sub_" + os.path.split(other.path)[1]
        return DicomSeries(volume=volume, slices=[], tags=dict(), path=path)

    @staticmethod
    def get_auto_windowing(image: np.array, width_n_stdev: int, exclude_black, exclude_white, n_bins:int):
        """without including the top 2.5% and bottom 2.5% pixel intensities (black or white) of the image,
        find the mean and width for the remaining values.
        The returned width is 1 std devs from the mean to the left and another to the right
        """
        pixel_values=image.flatten()
        hist, bin_edges = np.histogram(pixel_values, bins=n_bins)
        min = bin_edges[1]
        max = bin_edges[-2]
        # plt.hist(pixel_values, bins=n_bins)
        if exclude_black:
            pixel_values = pixel_values[pixel_values > min]
        if exclude_white:
            pixel_values = pixel_values[pixel_values < max]
        mean = np.mean(pixel_values)
        std = np.std(pixel_values)
        # plt.show()
        return mean + 1*std, width_n_stdev*std

    def find_chest_start(self):
        """finds the distance from left to right in the axial plane at the middle of the chest 
        image_start | ----distance--> |||chest|||"""
        WIDTH_N_STDEV = 2
        rough_window_center, rough_window_width = self.get_auto_windowing(
            self.volume, WIDTH_N_STDEV, exclude_black=True, exclude_white=False, n_bins=20)
        # print(rough_window_center, rough_window_width)
        # "left axial 0" is the axial plane at the middle of the chest
        slice = self.get_slice('left', 'axial', 0)
        slice = DicomSlice.window_image(slice, rough_window_center, rough_window_width)
        threshold = 150
        h = slice.shape[-2]
        # use only the central strip bc there is noise on the edges
        c_start, c_end = 2 * h // 5, 3 * h // 5
        col_mean = np.mean(slice[c_start:c_end, :], axis=-2)
        slice[c_start:c_end, :] = col_mean
        position = np.argwhere(col_mean > threshold)[0][0]
        return position

    def windowed_mip(self, laterality, view):
        """Find the chest and use only the voxels that exist after the chest (breasts and air) for 
        automatic windowing"""
        chest_start = self.find_chest_start()
        sag_mip = self.mip("all", "sagittal")
        breasts = sag_mip[:chest_start, :]
        window_center, window_width = self.get_auto_windowing(
            breasts, 6, exclude_black=True, exclude_white=False, n_bins=10)
        mip = self.mip(laterality, view)
        mip = DicomSlice.window_image(mip, window_center, window_width)
        return mip

    def get_number_of_slices(self, laterality: str, view: str):
        shape = self.get_volume_laterality(laterality).shape
        return (
            shape[2] if view == "axial" else shape[1] if view == "coronal" else shape[0]
        )

    def get_slice(self, laterality: str, view: str, slice_pos: int, volume=None) -> np.array:
        """Volume overrides get volume laterality"""
        volume = self.get_volume_laterality(laterality) if volume is None else volume
        assert view in [
            "axial", "coronal", "sagittal",
        ], f'view must be one of {["axial", "coronal", "sagittal"]}, not {view}'
        slice = (
            volume[:, :, slice_pos] if view == "axial"
            else volume[:, slice_pos, :] if view == "coronal"
            else volume[slice_pos, :, :]
        )
        return slice

    def show_slice(self, laterality:str, view:str, slice_pos:int, title=None, wc=window_center_val, ww=window_width_val):
        window_image = DicomSlice.window_image
        to_uint8 = DicomSlice.uint16_to_uint8
        title = f"{os.path.split(self.path)[1]}" if title is None else title
        slice = self.get_slice(laterality, view, slice_pos)
        image = to_uint8(window_image(slice, wc, ww))
        cv2.imshow(title, image)
        cv2.waitKey(show_time)

    def project(self):# , laterality: str, view: str):
        window_image = DicomSlice.window_image
        to_uint8 = DicomSlice.uint16_to_uint8
        get_image = lambda x: to_uint8(
            window_image(x, window_center_val, window_width_val)
        )
        mip_projection = self.mip("all", "sagittal")
        mip_projection = get_image(mip_projection)
        cv2.imshow(os.path.split(self.path)[1], mip_projection)
        cv2.waitKey(show_time)

    # def find_best_windowing(self):


if __name__ == "__main__":
    import matplotlib.pyplot as plt
    from PIL import Image
    import sys

    def series_subtraction(path_later, path_before):
        """volume later - before"""
        series_2 = DicomSeries.from_path(path_later)
        series_1 = DicomSeries.from_path(path_before)
        return series_2 - series_1

    # volume_folder = f"40100{str(i)}_eTHRIVE_Tra 1-6 dyn"
    study_path = "/Users/annotator/Desktop/MR scans/6673565251695351706f6b615653785a4b576c5357673d3d/yFUIc1QIEISR3x5aeIX2iJHb4uVv43gXJPzUa8isgwJNDOWHI3Oouz8NIpClQZYbDPHhxqALifek3BUQzN+3Qw=="
    volume_folder = "5_t1_fl3d_tra_dynaViews_HR_1-6_tra"
    series_path = os.path.join(study_path, volume_folder)
    volume_folder2 = "6_t1_fl3d_tra_dynaViews_HR_1-6_tra"
    series_path2 = os.path.join(study_path, volume_folder2)

    dcm_series2 = DicomSeries.from_path(series_path2)
    dif = series_subtraction(series_path2, series_path)
    mip = dif.mip("all", "sagittal")
    mip = DicomSlice.window_image(mip, window_center_val, window_width_val)
    # mip = dif.windowed_mip("all", "sagittal")
    plt.imshow(mip)
    plt.show()
    # cv2.imshow("mip", mip)
    # cv2.waitKey(0)