import numpy as np
import os
import pickle
import re
import skimage.io
import glob

from image_seg import config, utils
from os.path import join, isfile, exists

from sklearn.model_selection import train_test_split

###############################################################################
# Usage:                                                                      #
# dataset = DavisDataset("DAVIS", "480p")                                     #
###############################################################################


###############################################################################
#                              CLASS DICTIONARIES                             #
###############################################################################

class_names = {
    0: 'No Mask',
    1: 'Mask'
}

classes_to_index = dict([(e, i + 1) for i, e in enumerate(class_names.keys())])
index_to_classes = {v: k for k, v in classes_to_index.items()}
index_to_class_names = {v: class_names[k] for k, v in classes_to_index.items()}

###############################################################################
#                                CONFIGURATION                                #
###############################################################################


class DAVISConfig(config.Config):
    NAME = 'DAVIS'
    NUM_CLASSES = len(class_names) + 1
    BACKBONE = 'resnet101'


###############################################################################
#                                   DATASET                                   #
###############################################################################

class DAVISDataset(utils.Dataset):
    # TODO not working yet
    image_height = 480
    image_width = 854

    def __init__(self, root_dir=None, random_state=42):
        super(self.__class__, self).__init__(self)

        # Add classes (35)
        for class_id, class_name in class_names.items():
            self.add_class('DAVIS', classes_to_index[class_id], class_name)

        self.root_dir = root_dir
        self.random_state = random_state

    def load_data(self, root_dir, labeled=True, assume_match=False, val_size=0, provide_val = False, use_pickle=True):
        """Load a subset of the DAVIS image segmentation dataset.
        root_dir: Root directory of the train
        subset: Which subset to load: images will be looked for in 'subset_color' and masks will
        be looked for in 'subset_label' (will look for pickle file subset.pkl first)
        labeled: Whether the images have ground-truth masks
        assume_match: Whether to assume all images have ground-truth masks (ignored if labeled
        is False)
        val_size: applicable only when labeled = True. it is how much to split training for validation
        use_pickle: If False, forces a fresh load of the files
        """
        self.root_dir = root_dir

        pickle_path = self.root_dir + '.pkl'

        if use_pickle and val_size == 0 and isfile(pickle_path):
            self.load_data_from_file(pickle_path)
        else:
            # Check directories for existence
            print(self.root_dir)
            assert exists(join(self.root_dir))

            val = self.load_video(root_dir, labeled=labeled, assume_match=assume_match, provide_val=provide_val, val_size=val_size)

            self.save_data_to_file(pickle_path)

            if val is not None:
                return val

    def load_video(self, video_list_filename, labeled=True, assume_match=False, provide_val = False, val_size= 0):
        """Loads all the images from a particular video list into the dataset.
        video_list_filename: path of the file containing the list of images
        img_dir: directory of the images
        mask_dir: directory of the mask images, if available
        assume_match: Whether to assume all images have ground-truth masks
        """

        # Get list of images for this video
        video_file = open(video_list_filename, 'r')
        image_filenames = video_file.readlines()
        if provide_val != false :
            np.random.shuffle(image_filenames)
            num_val = ceil(val_size * len(image_filenames))
            val_filenames = image_filenames[:num_val]
            val = DAVISDataset()
            x = 0
            for img_mask_path in val_filenames:
                # Set paths and img_id
                if x == 0:
                    img_file = img_mask_path
                    img_id = img_file[:-4]
                    x = 1
                elif x == 1:
                    mask_file = img_mask_path
                    self.add_image("DAVIS", image_id=img_id, path=img_file, mask_path=mask_file)
                    x = 0
            train = image_filenames[num_val:]
            image_filenames = train
        image_filenames = image_filenames.split(" ")
        video_file.close()

        if image_filenames is None:
            print('No video list found at {}.'.format(video_list_filename))
            return
        x = 0
        # Generate images and masks
        for img_mask_path in image_filenames:
            # Set paths and img_id
            if x == 0:
                img_file = img_mask_path
                img_id = img_file[:-4]
                x = 1
            elif x == 1:
                mask_file = img_mask_path
                self.add_image("DAVIS", image_id=img_id, path=img_file, mask_path=mask_file)
                x = 0
        if provide_val != False and val is not None:
            return val

    def load_image(self, image_id):
        """Load the specified image and return a [H,W,3] Numpy array.
        image_id: integer id of the image
        """

        info = self.image_info[image_id]

        # If not a DAVIS dataset image, delegate to parent class
        if info["source"] != 'DAVIS':
            return super(self.__class__, self).load_image( image_id)

        # Load image
        path = join(self.root_dir, info['path'])
        image = skimage.io.imread(path)

        # If has an alpha channel, remove it for consistency
        if image.shape[-1] == 4:
            image = image[..., :3]

        return image

    def load_mask(self, image_id):
        """Generate instance masks for an image.
        image_id: integer id of the image
        Returns:
        masks: A bool array of shape [height, width, instance count] with
            one mask per instance.
        class_ids: a 1D array of class IDs of the instance masks.
        """

        info = self.image_info[image_id]

        # If not a DAVIS dataset image, delegate to parent class
        if info["source"] != "DAVIS":
            return super(self.__class__, self).load_mask(image_id)

        # Read the original mask image
        mask_path = join(self.root_dir, info['mask_path'])
        raw_mask = skimage.io.imread(mask_path)

        # unique is a sorted array of unique instances (including background)
        unique = np.unique(raw_mask)


             # section that removes/involves background
        index = np.searchsorted(unique, 255)
        if unique.size > index:
            unique = np.delete(unique, index, axis=0)

        # tensors!
        if len(raw_mask.shape) == 3:
           raw_mask = raw_mask[...,0]
        if raw_mask.shape[-1] == 3:
           raw_mask = raw_mask[..., 0]
        raw_mask = raw_mask.reshape(self.image_height, self.image_width, 1)

        # broadcast!!!!
        # k = instance_count
        # (h, w, 1) x (k,) => (h, w, k) : bool array
        masks = raw_mask == unique

        # get the actually class id
        # int(PixelValue / 1000) is the label (class of object)
        unique = np.floor_divide(unique, 1000)
        class_ids = np.array([classes_to_index[e] for e in unique])

        # Return mask, and array of class IDs of each instance.
        return masks, class_ids

    def load_data_from_file(self, filename):
        """Load images from pickled file.
        filename: name of the pickle file
        """
        with open(filename, 'rb') as f:
            self.image_info = pickle.load(f)

    def save_data_to_file(self, filename):
        """Save loaded images to pickle file.
        filename: name of the pickle file"""
        with open(filename, 'wb') as f:
            pickle.dump(self.image_info, f)

    def image_reference(self, image_id):
        """Return the image filename."""

        info = self.image_info[image_id]

        if info["source"] == "DAVIS":
            return info["path"]
        else:
            super(self.__class__, self).image_reference(image_id)


class MaskPropDavisDataset(object):
    # TODO: in init include way to download dataset
    # include download link and expected directory structure

    def __init__(self, directory, quality, val_videos=[]):
        """
        :param directory: root directory of the DAVIS dataset
        :param quality: video image quality (e.g. '480p')

        self.frame_pairs = an array of tuples of the form:
        (img_prev, img_curr, mask_prev, mask_curr) PATHS
        """

        # generate mask pairs

        self.trn_frame_pairs = []  # tuples of image and masks at t-1 and t
        self.val_frame_pairs = []

        image_dir = "%s/JPEGImages/%s/" % (directory, quality)
        mask_dir = "%s/Annotations/%s/" % (directory, quality)

        # CHANGE HERE: splitting into train_videos and val_videos
        videos = [x[len(image_dir):] for x in glob.glob(image_dir + "*")]
        self.trn_videos = list(set(videos) - set(val_videos))
        self.val_videos = val_videos

        # CHANGE HERE:
        for video in videos:

            frames = [x[len(image_dir) + len(video) + 1:-4] for x in glob.glob(image_dir + video + "/*")]
            frames.sort()

            for prev, curr in zip(frames[:-1], frames[1:]):

                image_prev = image_dir + video + "/" + prev + ".jpg"
                image_curr = image_dir + video + "/" + curr + ".jpg"
                mask_prev = mask_dir + video + "/" + prev + ".png"
                mask_curr = mask_dir + video + "/" + curr + ".png"

                if video in self.trn_videos:
                    self.trn_frame_pairs.append((image_prev, image_curr, mask_prev, mask_curr))
                else:
                    self.val_frame_pairs.append((image_prev, image_curr, mask_prev, mask_curr))

    def get_train_val(self, shuffle=True, random_state=42):
        if shuffle:
            np.random.seed(random_state)
            trn_frame_pairs = self.trn_frame_pairs.copy()
            val_frame_pairs = self.val_frame_pairs.copy()
            np.random.shuffle(trn_frame_pairs)
            np.random.shuffle(val_frame_pairs)
            return trn_frame_pairs, val_frame_pairs
        return self.trn_frame_pairs, self.val_frame_pairs

    def get_video_split(self):
        return self.trn_videos, self.val_videos

    def get_random_pair(self, val=True, random_state=42):
        # returns from training
        np.random.seed(random_state)
        if val:
            return self.val_frame_pairs[np.random.choice(range(len(self.val_frame_pairs)))]
        return self.trn_frame_pairs[np.random.choice(range(len(self.trn_frame_pairs)))]

    def data_generator(self, frame_pairs, get_model_input, batch_size=4, random_seed=None):
        """
        :param frame_pairs:
        :param get_model_input: function to get model input given a frame pair (i.e. apply Optical Flow)
        :param batch_size:
        :param random_seed:
        """

        if random_seed is not None:
            np.random.seed(random_seed)
        np.random.shuffle(frame_pairs)

        i = 0

        while True:
            batch_count = 0
            X = []
            y = []

            while batch_count < batch_size:
                # TODO first call doesn't take into account if frame_pairs is empty
                sample = frame_pairs[i]
                model_input, ground_truth = get_model_input(*sample)

                if model_input is not None and ground_truth is not None:
                    X.append(model_input)
                    # THIS PART IS WRONG: makes the output dimensions (batch_size, 480, 864, 1)
                    # But I don't think it impacts the output
                    y.append(np.expand_dims(ground_truth, axis=3))
                    batch_count = batch_count + 1

                i = i + 1  # keeps track of where we are in dataset

                # restart -> may cause repeats in samples within epoch or validation run
                if i >= len(frame_pairs):
                    i = 0  # go back to beginning
                    np.random.shuffle(frame_pairs)

            X = np.array(X)
            y = np.array(y)

            yield X, y

