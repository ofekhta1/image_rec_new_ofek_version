import numpy as np
from insightface.utils.face_align import norm_crop
import os
from . import util;
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import cosine_similarity
from .model_loader import ModelLoader
from joblib import load
import cv2
from PIL import Image

class ImageHelper:
  
    ALLOWED_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".tif",
        ".tiff",
        ".webp"
    }
    # Load model on startup
    def __init__(self, detector,detector_zoomed,embedder,groups,emb_manager, UPLOAD_FOLDER, STATIC_FOLDER):
        self.detector = detector
        self.detector_zoomed = detector_zoomed
        self.embedder = embedder
        self.UPLOAD_FOLDER = UPLOAD_FOLDER
        self.STATIC_FOLDER = STATIC_FOLDER
        self.groups=groups;
        self.emb_manager=emb_manager;
    

    def __align_single_image(self, face, selected_face, filename, img):
        landmarks = face["kps"].astype(int)
        aligned_filename = f"aligned_{selected_face}_{filename}"
        aligned_path = os.path.join(self.STATIC_FOLDER, aligned_filename)
        aligned_img = norm_crop(img, landmarks, 112, "arcface")
        cv2.imwrite(aligned_path, aligned_img)
        return aligned_filename



    def detect_faces_in_image(self, filename, images):
        img, faces = self.__extract_faces(filename)
        boxes=[]
        if faces:
            for face in faces:
                landmarks = face["kps"].astype(int)
                for point in landmarks:
                    cv2.circle(
                        img,
                        (int(point[0]), int(point[1])),
                        2,
                        (0, 255, 0),
                        -2,
                    )
                box=face['bbox'].astype(int).tolist();
                boxes.append(box)
            detected_filename = "detected_" + filename
            detected_path = os.path.join(self.STATIC_FOLDER, detected_filename)
            # message += f"path {detected_path}. "
            cv2.imwrite(detected_path, img)
            images.append(detected_filename)
            return len(faces),boxes
        else:
            images.append(filename)
   
    def create_aligned_images(self, filename, images):
        img, faces = self.__extract_faces(filename)
        face_count = 0

        for face in faces:
            aligned_filename = self.__align_single_image(
                face, face_count, filename, img
            )
            images.append(aligned_filename)
            face_count += 1
        return face_count

    def __extract_faces(self, filename):
        path = os.path.join(self.UPLOAD_FOLDER, filename)
        img = cv2.imread(path)
        try:
            close_faces=self.detector_zoomed.get(img)
            far_faces=self.detector.get(img)
            faces=far_faces.copy();
            for j in range(len(close_faces)):
                        duplicate=False;
                        for far_face in far_faces:
                            if(util.are_bboxes_similar(close_faces[j]['bbox'],far_face['bbox'],20)):
                                duplicate=True;
                        if(not duplicate):
                            faces.append(close_faces[j])
            return img, faces
        except:
            return img,None;


    @staticmethod
    def extract_embedding(face_data):
        try:
            if face_data and "embedding" in face_data:
                embedding = face_data["embedding"]
                return embedding
            else:
                print("No faces detected.")  # Debug log
                return None
        except Exception as e:
            print("Error during embedding extraction:", e)  # Debug log
            return None
        
    def generate_all_emb(self,filename,save=True):
        errors=[];
        embedding=None;
        embeddings=[];
        if self.embedder:
            img,faces=self.__extract_faces(filename);                
            if faces:
                for i in range(len(faces)):
                    embedding=self.embedder.get(img,faces[i]);
                    embeddings.append(np.array(embedding));
                    if(save):
                        self.emb_manager.add_embedding(embedding,f"aligned_{i}_{filename}");
            else:
                print("No faces detected.")  # Debug log
                errors.append("No faces detected in one or both images.")
        else:
            errors.append("Error: Embedder model not initialized.")
        return embeddings,errors;



    @staticmethod
    def points(numpoints,max_val,template_path,image_path):
      MIN_MATCH_COUNT = numpoints
      img1 = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE) # queryImage
      img2 = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE) # trainImage
      sift = cv2.SIFT_create()
      kp1, des1 = sift.detectAndCompute(img1,None)
      kp2, des2 = sift.detectAndCompute(img2,None)
      FLANN_INDEX_KDTREE = 1
      index_params = dict(algorithm = FLANN_INDEX_KDTREE, trees = 5)
      search_params = dict(checks = 50)
      flann = cv2.FlannBasedMatcher(index_params, search_params)
      matches = flann.knnMatch(des1,des2,k=2)
      good = []
      M = 0
      for m,n in matches:
       if m.distance < 0.7*n.distance:
        good.append(m)
       if (len(good)>MIN_MATCH_COUNT) and (max_val>= - 0.2 or len(good)>=60):
         src_pts = np.float32([ kp1[m.queryIdx].pt for m in good ]).reshape(-1,1,2)
         dst_pts = np.float32([ kp2[m.trainIdx].pt for m in good ]).reshape(-1,1,2)
         M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC,5.0)
         matchesMask = mask.ravel().tolist()
         h,w = img1.shape
         pts = np.float32([ [0,0],[0,h-1],[w-1,h-1],[w-1,0] ]).reshape(-1,1,2)
         if(M is not None):
          dst = cv2.perspectiveTransform(pts,M)
          img2 = cv2.polylines(img2,[np.int32(dst)],True,255,3, cv2.LINE_AA)
       else:
         #print( "Not enough matches are found - {}/{}".format(len(good), MIN_MATCH_COUNT) )
         matchesMask = None
      draw_params = dict(matchColor = (0,255,0), # draw matches in green color
      singlePointColor = None,
      matchesMask = matchesMask, # draw only inliers
      flags = 2)
      img3 = cv2.drawMatches(img1,kp1,img2,kp2,good,None,**draw_params)
      if (len(good) >= MIN_MATCH_COUNT) and (max_val>= - 0.2 or len(good)>=60) and M is not None :
        print("The object (e.g., tattoo) exists in both images!")
        #plt.imshow(img3, 'gray')
        #plt.show(block=True)
        #create_combined_file()
      else:
     #plt.imshow(img3, 'gray')
     #plt.show(block=True)
         print("The object (e.g., tattoo) does NOT exist or the similarity is too low.")
      if(M is not None):
            return len(good)
      else:
          return 0

    

     
    def create_combined_file(max_loc,image,template):
        h, w = image.shape[:2]
        top_left = max_loc
        bottom_right = (top_left[0] + w, top_left[1] + h)
        detected_object = template[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]]
        detected_object_resized = cv2.resize(detected_object, (image.shape[1], image.shape[0]))
        combined_image = np.hstack((image, detected_object_resized))

    # output_dir = create_output_directory(image_files, images_dir + r"\archive")
    # combined_image_path = os.path.join(output_dir, "combined_" + image_files)
    # cv2.imwrite(combined_image_path, combined_image)
   
    @staticmethod
    def load_model(model_path):
    # Load the saved model
     return load(model_path)


    @staticmethod
    def allowed_file(filename):
        extension=os.path.splitext(filename)[1];
        return extension.lower() in ImageHelper.ALLOWED_EXTENSIONS;



    def generate_embedding(self,filename,selected_face,save=True):
        errors=[];
        embedding=None;
        if self.embedder:
            img,faces=self.__extract_faces(filename)
            if faces:
                if selected_face == -2 or len(faces) == 1:
                    i=0
                else:
                    i=selected_face
                embedding=self.embedder.get(img,faces[i]);
                if(save):
                    self.emb_manager.add_embedding(embedding,f"aligned_{i}_{filename}");

            else:
                print("No faces detected.")  # Debug log
                errors.append("No faces detected in one or both images.")
        else:
            errors.append("Error: Embedder model not initialized.")
        return embedding,errors;

    def get_similar_images(self,user_embedding,filename,k=5):
        np_emb=np.array(user_embedding).astype("float32").reshape(1,-1)
        result=self.emb_manager.search(np_emb,k);
        filtered=[]
        seen_distances=[]
        for r in result:
            if r["distance"] not in seen_distances:
                seen_distances.append(r["distance"])
                i=r["index"];
                name=self.emb_manager.get_name(i);
                if(name.split('_')[-1]!=filename.split('_')[-1]):
                    filtered.append({"index":i,"name":name})
        valid=[x for x in filtered if len(emb := self.emb_manager.get_embedding(x['index']))>0 
                and not np.allclose(emb,user_embedding,rtol=1e-5,atol=1e-8)]
        return valid;
    def filter(self,threshold):
        manager=self.emb_manager
        errors=[]
        original_length=len(manager.db_embeddings["names"]);
        for name in manager.db_embeddings["names"]:
            embedding=manager.get_embedding_by_name(name)
            valid=self.get_similar_images(embedding,name.split('_')[-1]);
            for image in valid:            
                match=image['name'];
                _,facenum,filename=match.split('_');
                similarity=util.calculate_similarity(
                    self.emb_manager.get_embedding(image['index'])
                    ,embedding);
                if(similarity>threshold):
                    manager.remove_embedding_by_index(image['index']);
        filtered_length=len(manager.db_embeddings["names"]);
        return original_length-filtered_length;

    def enhance_image(self,filename):
        image_path = os.path.join(self.UPLOAD_FOLDER, filename)
        # Load the image
        image = cv2.imread(image_path)
        if image is None:
            print(f"The image at {image_path} could not be loaded.")
            return

        # Apply slight Gaussian blur to the image to reduce noise
        blurred = cv2.GaussianBlur(image, (3, 3), 0)

        # Sharpen the image by subtracting the Gaussian blur from the original image
        sharpened = cv2.addWeighted(image, 1.5, blurred, -0.5, 0)

        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab = cv2.cvtColor(sharpened, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l2 = clahe.apply(l)
        lab = cv2.merge((l2, a, b))
        enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        return enhanced

    def get_most_similar_image(self,selected_face,filename):
        user_image_path = os.path.join(self.UPLOAD_FOLDER, filename)
        errors=[]
        most_similar_image=None;
        most_similar_face=-2;
        max_similarity=-1;
        facenum=-2;
        temp_err=[]
        aligned_filename=f"aligned_{0 if selected_face == -2 else selected_face}_{filename}";
        embedding=self.emb_manager.get_embedding_by_name(aligned_filename)
        if len(embedding)>0:
            user_embedding=embedding;
        else:
            user_embedding,temp_err=self.generate_embedding(filename,selected_face);
            errors=errors+temp_err;
        if len(errors)==0:
            valid=self.get_similar_images(user_embedding,filename);
            for image in valid:
                try:  
                    match=image['name'];
                    _,facenum,filename=match.split('_',2);
                    similarity=util.calculate_similarity(
                        self.emb_manager.get_embedding(image['index'])
                        ,user_embedding);
                    if(similarity>max_similarity):
                        max_similarity=similarity;
                        most_similar_image=filename;
                        most_similar_face=int(facenum);
                except Exception as e:
                    # template_matching
                    print(f"failed to match image {match} because:\n{e}");
            if len(valid)==0:
                errors.append("No unique matching faces found!");
        elif len(embedding)==0:
            template=cv2.imread(user_image_path)
            with os.scandir(self.UPLOAD_FOLDER) as entries:
                for entry in entries:
                    if entry.is_file() and ImageHelper.allowed_file(entry.name):
                        if (entry.name != filename) and (filename not in entry.name) and (entry.name != filename.replace("enhanced_", "")):
                            img=cv2.imread(entry.path);
                            image_height, image_width, _ = img.shape
                            template = cv2.resize(template, (image_width, image_height))
                            template = template.astype(img.dtype)
                            result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
                            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                            if max_val >= max_similarity:
                                h, w, _ = template.shape
                                top_left = max_loc
                                bottom_right = (top_left[0] + w, top_left[1] + h)
                                cv2.rectangle(img, top_left, bottom_right, (0, 255, 0), 2)
                                most_similar_image = entry.name
                                max_similarity =max_val
        errors=errors+temp_err;
        return most_similar_image,most_similar_face,max_similarity,errors;


    def get_most_similar_image_new(self,selected_face,filename,fullfilename):
        user_image_path = os.path.join(self.UPLOAD_FOLDER, filename)
        errors=[]
        most_similar_image=None;
        max_similarity=-1;
        facenum=-2;
        aligned_filename=f"aligned_{0 if selected_face == -2 else selected_face}_{filename}";
        embedding=self.emb_manager.get_embedding_by_name(aligned_filename)
        if len(embedding)>0:
            user_embedding=embedding;
        else:
            user_embedding,temp_err=self.generate_embedding(user_image_path,selected_face);
            errors=errors+temp_err;
        if (embedding is not None): #and len(errors)==0  
            sum_points=[0]
            with os.scandir(self.UPLOAD_FOLDER) as entries:
                for entry in entries:
                    if  (entry.name != filename) and (filename not in entry.name) and (entry.name != filename.replace("enhanced_", "")):
                            if entry.is_file() and ImageHelper.allowed_file(entry.name):
                                embeddings,emb_errors =self.generate_all_emb(entry.name,False);
                                if(len(emb_errors)>0 or len(embeddings)==0):
                                    errors+=emb_errors;  
                                    
                                if user_embedding is not None:
                                    for embedding in embeddings:
                                        similarity = util.calculate_similarity(user_embedding, embedding)
                                        if similarity > max_similarity:
                                            max_similarity = similarity
                                            most_similar_image = entry.name
                                else:
                                    img=cv2.imread(entry.path);
                                    template = cv2.imread(fullfilename) 
                                    image_height, image_width, _ = img.shape
                                    template = cv2.resize(template, (image_width, image_height))
                                    template = template.astype(img.dtype)
                                    result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
                                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                                    threshold = 0.34
                                    if max_val >= threshold:
                                        h, w, _ = template.shape
                                        top_left = max_loc
                                        bottom_right = (top_left[0] + w, top_left[1] + h)
                                        cv2.rectangle(img, top_left, bottom_right, (0, 255, 0), 2)
                                        most_similar_image = entry.name
                                        max_similarity =max_val
                                    #create_combined_file() 
                                    elif(max_val>=0.273):
                                        leng=  ImageHelper.points(4,max_val,fullfilename,entry.path)
                                        if(leng>=4):
                                            if max(sum_points) < leng:
                                                most_similar_image = entry.name
                                                max_similarity =max_val
                                            sum_points.append(leng)
                                    elif(max_val>=0.2):
                                        leng=  ImageHelper.points(5,max_val,fullfilename,entry.path)
                                        if(leng>=5):
                                            
                                            if max(sum_points) < leng:
                                                most_similar_image = entry.name
                                                max_similarity =max_val
                                            sum_points.append(leng) 
                                    else: 
                                        leng= ImageHelper.points(15,max_val,fullfilename,entry.path)
                                        if(leng>=15):
                                            if max(sum_points) < leng:
                                                most_similar_image = entry.name
                                                max_similarity =max_val
                                            sum_points.append(leng)
                                                  
            if(most_similar_image is None):
                errors.append("No images found")
                                                    #print("The object (e.g., tattoo) exists in both images!")
                                               

        # else:
        #     errors=errors+temp_err;
        return most_similar_image,int(facenum),max_similarity,errors;
    
    def cluster_images(self,max_distance,min_samples):
        # Assuming 'embeddings' is a list of your 512-dimensional embeddings
        similarity_matrix = cosine_similarity(self.emb_manager.db_embeddings["embeddings"])
        similarity_matrix = np.clip(similarity_matrix, -1, 1)
        # Apply DBSCAN

        dbscan = DBSCAN(eps=max_distance, min_samples=min_samples, metric="precomputed")
        labels = dbscan.fit_predict(1 - similarity_matrix)  # Convert similarity to distance
        unique_values = np.unique(labels)
        index_groups = {value: np.where(labels == value)[0] for value in unique_values}
        value_groups = {
            int(key): [self.emb_manager.db_embeddings["names"][index] for index in indexes]
            for key, indexes in index_groups.items()
        }
        return value_groups;