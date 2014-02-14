import numpy
import cellh5
import pandas
import os
import collections
import functools
import time
import cProfile
import re
import datetime
import pylab
from collections import OrderedDict
from itertools import izip_longest
from matplotlib.mlab import PCA
from matplotlib.backends.backend_pdf import PdfPages
from cecog.util.color import rgb_to_hex
from sklearn import hmm
from estimator import HMMConstraint, HMMAgnosticEstimator, normalize
hmm.normalize = lambda A, axis=None: normalize(A, axis, eps=10e-99)

def hex_to_rgb(hex_string):
    """
    Converts the hex representation of a RGB value (8bit per channel) to
    its integer components.

    Example: hex_to_rgb('#559988') = (85, 153, 136)
             hex_to_rgb('559988') = (85, 153, 136)

    @param hexString: the RGB value
    @type hexString: string
    @return: RGB integer components (tuple)
    """
    if hex_string[:2] == '0x':
        hex_value = eval(hex_string)
    elif hex_string[0] == '#':
        hex_value = eval('0x'+hex_string[1:])
    else:
        hex_value = eval('0x'+hex_string)
    b = hex_value & 0xff
    g = hex_value >> 8 & 0xff
    r = hex_value >> 16 & 0xff
    return (r/255.0, g/255.0, b/255.0)

                         

class CellH5Analysis(object):
    def __init__(self, name, mapping_files, cellh5_files, output_dir=None, 
                       sites=None, rows=None, cols=None, locations=None):
        self.name = name
        self.mapping_files = mapping_files
        self.cellh5_files = cellh5_files
        self.output_dir = output_dir
        self.time_lapse = {}
        
        # read mappings for all plates
        mappings = []
        for plate_name, mapping_file in mapping_files.items():
            assert plate_name in cellh5_files.keys()
            cellh5_file = cellh5_files[plate_name]
            plate_cellh5  = cellh5.CH5MappedFile(cellh5_file)
            plate_cellh5.read_mapping(mapping_file, sites=sites, rows=rows, cols=cols, locations=locations, plate_name=plate_name)
            plate_mappings = plate_cellh5.mapping
            self.time_lapse[plate_name] = plate_cellh5.current_pos.get_time_lapse() / 60.0
            plate_cellh5.close()
            
            mappings.append(plate_mappings)
        self.mapping = pandas.concat(mappings, ignore_index=True)
        del mappings

        self.set_output_dir(output_dir)
        
    def set_output_dir(self, output_dir):
        if self.output_dir is None:
            self.output_dir = self.name +"/" + datetime.datetime.now().strftime("%y-%m-%d-%H-%M")
            #self.output_dir += "-p%d-k%s-n%f-g%f" % (self.pca_dims, self.kernel, self.nu, self.gamma)
            try:
                os.makedirs(self.output_dir)
            except:
                pass
        print "Output Directory: ", self.output_dir
        

    def output(self, file_):
        file_ = self.str_sanatize(file_)
        return os.path.join(self.output_dir, file_) 
        
    @staticmethod    
    def str_sanatize(input_str):
        input_str = input_str.replace("/","_")
        input_str = input_str.replace("#","_")
        input_str = input_str.replace(")","_")
        input_str = input_str.replace("(","_")
        return input_str
                
    def read_events(self, onset_frame=4, events_before_frame=99999):   
        self.mapping['Event labels'] = -1   
        self.mapping['Event ids'] = -1
        event_label_list = []
        event_id_list = []   
        for _, (plate, w, p) in self.mapping[['Plate', 'Well','Site']].iterrows(): 
            try:
                cellh5file = cellh5.CH5File(self.cellh5_files[plate])
                cellh5pos = cellh5file.get_position(w, str(p))
            except:
                print "Positon", (w, p), "is corrupt. Process again with CellCognition"
                cellh5file.close()
                continue
            event_ids = cellh5pos.get_events()
            
            event_ids = [e for e in event_ids if cellh5pos.get_time_idx(e[onset_frame]) < events_before_frame]
            
            event_id_list.append(event_ids)
            event_label_list.append([cellh5pos.get_class_label(e) for e in event_ids])
            print "Read events from ch5:", plate, w, p, "with", list(self.get_treatment(plate, w, p))
            cellh5file.close()
        self.mapping['Event labels'] = pandas.Series(event_label_list)
        self.mapping['Event ids'] = pandas.Series(event_id_list)
        
    def get_treatment(self, plate, w, p):
        return list(self.mapping[
                                (self.mapping['Plate'] == plate) &
                                (self.mapping['Well'] == w) &
                                (self.mapping['Site'] == p)
                                ][['siRNA ID', 'Gene Symbol']].iloc[0])
    def track_full_events(self):
        self.mapping['Event track labels'] = -1   
        self.mapping['Event track ids'] = -1 
        all_track_ids = []
        all_track_labels = []
        
        for _, (plate, w, p, event_ids) in self.mapping[['Plate', 'Well', 'Site', 'Event ids']].iterrows(): 
            try:
                cellh5file = cellh5.CH5File(self.cellh5_files[plate])
                cellh5pos = cellh5file.get_position(w, str(p))
            except:
                print "Positon", (w, p), "is corrupt. Process again with CellCognition"
                cellh5file.close()
                continue
            
            track_labels_list = []
            track_id_list = []
            
            for _, e_idx in enumerate(event_ids):   
                start_idx = e_idx[-1]
                track_ids = e_idx + cellh5pos.track_first(start_idx)
                
                track_labels_list.append(cellh5pos.get_class_label(track_ids))
                track_id_list.append(track_ids)
            all_track_ids.append(track_id_list)
            all_track_labels.append(track_labels_list)
            print "Tracking events from ch5:", plate, w, p, "with", list(self.get_treatment(plate, w, p))
            cellh5file.close()
        self.mapping['Event track labels'] = pandas.Series(all_track_labels)
        self.mapping['Event track ids'] = pandas.Series(all_track_ids)

        print ' ...done'
        
    def setup_hmm(self, hmm_n_classes, hmm_n_obs, hmm_constraint_file):
        self.hmm_n_classes = hmm_n_classes
        self.hmm_n_obs = hmm_n_obs
        self.hmm_constraint_file = hmm_constraint_file
        
        constraints = HMMConstraint(self.hmm_constraint_file)
        
        transmat = numpy.array([
                                [1.0, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.9],
                                [0.0, 1.0, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1],
                                [0.0, 0.1, 1.0, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1],
                                [0.0, 0.0, 0.1, 1.0, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1],
                                
                                [0.0, 0.0, 0.0, 0.0, 90 , 1  , 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 60 ],
                                [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1],
                                [0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 1.0, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1],
                                [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 1.0, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1],
                                
                                [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 90 , 1  , 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 60 ],
                                [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1],
                                [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 1.0, 0.9, 0.0, 0.0, 0.0, 0.0, 0.1],
                                [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 1.0, 0.9, 0.0, 0.0, 0.0, 0.1],
                                
                                [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 90 , 1  , 0.0, 0.0, 60 ],
                                [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.9, 0.0, 0.1],
                                [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 1.0, 0.9, 0.1],
                                [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 1.0, 0.1],
                                
                                [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
                                ])
        transmat = normalize(transmat, axis=1, eps=0 )
        
        assert transmat.shape[0] == self.hmm_n_classes
        assert transmat.shape[1] == self.hmm_n_classes
        
        est = HMMAgnosticEstimator(self.hmm_n_classes, 
                                   transmat, 
                                   numpy.ones((self.hmm_n_classes, self.hmm_n_obs)), 
                                   numpy.ones((self.hmm_n_classes, )))
        
        est.constrain(constraints)
        self.hmm = hmm.MultinomialHMM(n_components=est.nstates, transmat=transmat, startprob=est.startprob, init_params="")
        self.hmm._set_emissionprob(est.emis)
               
    def predict_hmm(self, class_selector='Event track labels'):
        print 'Predict hmm',
        self.mapping['Event HMM track labels'] = -1 
        all_hmm_labels_list = []
        for _, (plate, w, p, track_labs) in self.mapping[['Plate', 'Well', 'Site', class_selector]].iterrows(): 
            print plate, w, p 
            hmm_labels_list = []
            for t in track_labs:   
                hmm_class_labels = self.hmm.predict(numpy.array(t-1)) + 1
                hmm_labels_list.append(hmm_class_labels)
            all_hmm_labels_list.append(hmm_labels_list)
        self.mapping['Event HMM track labels'] = pandas.Series(all_hmm_labels_list)
        print 'done'
            
                            
        
    def event_curves(self, event_selector, 
                           title,
                           region_name,
                           feature_name,
                           with_fate,
                           cmap,
                           xlim,
                           ylim,
                           ):
        pp = PdfPages(self.output("%s.pdf") % title)
        
        
        time_unit = 'min'
        
        for w, p in sorted(self.tracks):
            cnt = 0
            f = pylab.figure(figsize=(8, 8))
            ax = pylab.gca()
            
            
            feature_table = self.mcellh5.get_position(w,str(p)).get_object_features(region_name)
            feature_idx = self.mcellh5.get_object_feature_idx_by_name(region_name, feature_name)

            id_selector = 'track_ids'
            fate_ = 'short'
            if with_fate:
                id_selector = 'track_ids'
                fate_ = 'long'
            
            all_feature_values = [feature_table[t, feature_idx] for t in self.tracks[(w,p)][id_selector]]
                
            feature_min = SECURIN_BACKGROUND #numpy.min(map(numpy.min, all_feature_values))
                
            #print "FEATURE_MIN", feature_min
            for line, feature_values in zip(self.tracks[(w,p)][event_selector], all_feature_values):
                x_values = numpy.array(map(int,list(line)))
                if numpy.max(feature_values) < 15:
                    print 'excluding event due to low signal'
                    continue
                values = numpy.array(feature_values - feature_min) 
                values = values / numpy.mean(values[(self.onset_frame-1):(self.onset_frame+2)])
                self._plot_curve(x_values[:len(feature_values)], values, cmap, ax)
  

            pylab.vlines(0, ylim[0], ylim[1], 'k', '--', label='NEBD')
            title = '%s - %s (%s)'% tuple(list(self.mcellh5.get_treatment_of_pos(w, p)) + [w,])
            ax.set_title(title)
            ax.set_xlabel('Time (%s)' % time_unit)
            ax.set_ylabel('Fluorescence (AU)')
            ax.set_ylim(ylim)
            ax.set_xlim(xlim)
            ax.spines["right"].set_visible(False)
            ax.spines["top"].set_visible(False)
            ax.get_xaxis().tick_bottom()
            ax.get_yaxis().tick_left()
            
            pylab.savefig(pp, format='pdf')
            for fmt in OUTPUT_FORMATS:
                pylab.savefig(self.output('securin_2_all_%s_%s.%s' % (fate_, title, fmt)))
            pylab.clf()    
        pp.close()
    

             
    def plot_track_order_map(self, track_selection, color_maps, track_short_crop_in_min=240):
        fig = pylab.figure()
        n = len(track_selection)
        for _, (plate, w, p) in self.mapping[['Plate', 'Well', 'Site']].iterrows(): 
            try:
                cellh5file = cellh5.CH5File(self.cellh5_files[plate])
            except:
                print "File", (plate, w, p), "is corrupt. Process again with CellCognition"
                cellh5file.close()
                continue

            idx = ((self.mapping['Plate'] == plate) &
                   (self.mapping['Well'] == w) &
                   (self.mapping['Site'] == p))
            treatment = self.get_treatment(plate, w, p)
            for k, class_selector in enumerate(track_selection):
                cmap = color_maps[k]
                tracks = self.mapping.loc[idx][class_selector].iloc[0]
                track_lens = map(len, tracks)
                if len(track_lens) > 0:
                    max_track_length = max(track_lens)
                    n_tracks = len(tracks)
                    img = numpy.zeros((n_tracks, max_track_length), dtype=numpy.uint8)
                    
                    track_crop_frame = int(track_short_crop_in_min/self.time_lapse[plate] + 0.5)
                    
                    def my_cmp(x,y):
                        counter = lambda x, items: reduce(lambda a,b:a+b, [list(x).count(xx) for xx in items])
                        tmp =  cmp(counter(x, [2,3,4]), counter(y, [2,3,4]))
                        return tmp if tmp!=0 else cmp(len(x),len(y)) 
                    
                    for i, t in enumerate([tmp[0] for tmp in sorted(zip(tracks, self.mapping[idx][track_selection[-1]].iloc[0]), cmp=my_cmp, key=lambda x:x[1])]):
                        img[i,:len(t)] = t
                      
                    pylab.clf()
                    ax = pylab.subplot(111)
                    ax.matshow(img[:,:track_crop_frame], cmap=cmap, vmin=0, vmax=cmap.N-1)
                    title = '%s - %s (%s) %s' % tuple(list(treatment) + [w, 'short']) 
                    ax.set_title(title)
                    pylab.axis('off')
                    extent = ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
                    #fig.savefig(self.output('tracks_short_%s_%d.png' % (title, TRACK_IMG_CROP)), bbox_inches=extent)  

                    pylab.clf()
                    ax = pylab.subplot(111)
                    ax.matshow(img, cmap=cmap, vmin=0, vmax=cmap.N-1) 
                    ax.set_title(title)
                    pylab.axis('off')
                    extent = ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
                    #fig.savefig(self.output('tracks_full_%s_%d.png' % (title, int(max_track_length*self.time_lapse))), bbox_inches=extent)
                    
                    pylab.show()
                else:
                    print plate, w, p, 'Track has len zero. Nothing to plot'
 
                    
                   
                
    
    
    def plot_mitotic_timing(self, track_selector):
        
        pp = PdfPages(self.output('_mitotic_timing.pdf'))
        f = pylab.figure(figsize=(20,8))
        mito_timing = OrderedDict()
        mito_class = OrderedDict()
        
        xticklabels=[]
        
        for w, p in sorted(self.tracks.keys()):
            
            exp_content = OrderedDict()
        
            mito_classes = ['mito_int',
                            'mito_int_mito_int_mito',
                            'mito_int_mito_int_apo',
                            'mito_int_apo',
                            'mito_int_mito_apo',
                            'mito_apo',
                            'mito_unclassified']

            mito_timing[(w,p)] = []
            mito_class[(w,p)] = []
            if (w,p) not in self.tracks:
                continue
            
            for m_idx, m_class in enumerate(mito_classes):
                for t_ in self.tracks[(w,p)][m_class]:
                    t = t_[1]
                    track_str = "".join(map(lambda x: "%02d" % x, t))
                    mito_re = re.search(r'01+(?P<mito>(02|03)+)', track_str)
                    if mito_re is not None:
                        span = mito_re.span('mito')
                        mito_timing[(w,p)].append((span[1]/2 - span[0]/2) * self.time_lapse )
                        mito_class[(w,p)].append(m_idx)
                    else:
                        pass
                
            treatment = self.mcellh5.get_treatment(w, p)[1]
            xticklabels.append("%s_%02d" % (w,p))
        
        from itertools import izip_longest
        import csv

        with open(self.output('__mito_timing.txt'), 'wb') as f:
            writer = csv.writer(f, delimiter='\t')
            writer.writerow(xticklabels)
            writer.writerows(izip_longest(*mito_timing.values(), fillvalue=""))
               
        with open(self.output('__mito_classes.txt'), 'wb') as f:
            writer = csv.writer(f, delimiter='\t')
            writer.writerow(xticklabels)
            writer.writerows(izip_longest(*mito_class.values(), fillvalue="")) 
        
        colors = ['g', 'g',] + ['r']*5 + ['b']*5 + ["#ffa500"]*3 + ['r']*5 + ['b']*5 + ["#ffa500"]*3 + ['k']*50
#         ax = p(mito_timing.values(), xticklabels=xticklabels, colors=colors, spread_type='g', spread=0.1)
        ax = pylab.boxplot(mito_timing.values())
        ax = pylab.gca()
        ax.set_xticklabels(xticklabels, rotation=90)
        ax.set_title('Mitotic Timing')
        ax.set_ylabel('Mitotic timing (min)')
        pylab.tight_layout()
        pylab.savefig(pp, format='pdf')
        
        pp.close()
    
    
if __name__ == '__main__':
    pm = CellH5Analysis('test_fate', 
                        {'002338': "M:/experiments/Experiments_002300/002338/002338/_meta/Cecog/Mapping/002338.txt"}, 
                        {'002338': "M:/experiments/Experiments_002300/002338/002338/_meta/Analysis/hdf5/_all_positions.ch5"}, 
                        sites=(1,),
                        rows=("B", "C" ), 
                        cols=(5,9),
                        )
    pm.read_events(5, 90)
    pm.track_full_events()
    pm.setup_hmm(17, 5, 'hmm_constraints/graph_5_to_17_ms_special.xml')
    pm.predict_hmm()
    import matplotlib
    cmap = matplotlib.colors.ListedColormap(map(lambda x: hex_to_rgb(x), 
                                                   ['#FFFFFF', 
                                                    '#00ff00', 
                                                    '#ff8000',
                                                    '#d28dce',
                                                    '#0055ff',
                                                    '#aa5500', 
                                                    '#ff0000',
                                                    '#ffff00']), 'classification_cmap')
    CMAP17 = matplotlib.colors.ListedColormap(map(lambda x: hex_to_rgb(x), 
                                                   ['#FFFFFF', 
                                                    '#AAAAAA', 
                                                    '#0000FF',
                                                    '#0000FF',
                                                    '#0000FF',
                                                    '#AAAAAA', 
                                                    '#0000FF',
                                                    '#0000FF',
                                                    '#0000FF',
                                                    '#AAAAAA', 
                                                    '#0000FF',
                                                    '#0000FF',
                                                    '#0000FF',
                                                    '#AAAAAA', 
                                                    '#0000FF',
                                                    '#0000FF',
                                                    '#0000FF',
                                                    '#FF0000',
                                                    '#00FF00']), 'cmap17')  
    pm.plot_track_order_map(['Event track labels', 'Event HMM track labels'], [cmap, CMAP17])